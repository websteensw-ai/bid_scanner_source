"""논술랩 웹앱 (FastAPI + Jinja2 + htmx). Vercel 진입점: web.main:app

학습 엔진·콘텐츠·판정(src/learning)은 그대로 쓰고, 화면만 서버 렌더링으로 그린다.
- 세션: 서명된 쿠키 (SESSION_SECRET)
- 테스트 로그인: 브라우저마다 별도의 데모 학습자 id 를 발급해, 방문자끼리 기록이 섞이지 않는다
- 기록: web/store.py (운영: Supabase RPC / 로컬: 메모리)
"""
import hmac
import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.sessions import SessionMiddleware

from src.core.config import get_settings
from src.learning.analyzer import get_analyzer
from src.learning.content import active_version, available_versions, count_chars, load_pack
from src.learning.engine import Engine, LearningError, answered
from src.learning.entry import STUDENT_MESSAGE, EntryDecision
from src.learning.levels import (
    CRITERION_LABEL,
    CRITERION_PLAIN,
    SUPPORT_LABEL,
    Criterion,
    SupportType,
    level_label,
)
from src.learning.state import ReviewRecord
from web.store import get_store

ROOT = Path(__file__).resolve().parents[1]
settings = get_settings()

ON_VERCEL = bool(os.getenv("VERCEL"))
_secret = os.getenv("SESSION_SECRET")
if not _secret:
    if settings.app_env == "production" or ON_VERCEL:
        raise RuntimeError("SESSION_SECRET 환경변수가 필요합니다.")
    _secret = "dev-only-session-secret"

app = FastAPI(title="논술랩 · 기초 다지기", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=_secret, session_cookie="elenchos_session",
                   max_age=60 * 60 * 24 * 14, same_site="lax",
                   https_only=settings.app_env == "production" or ON_VERCEL)

env = Environment(loader=FileSystemLoader(ROOT / "web" / "templates"),
                  autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
templates = Jinja2Templates(env=env)
env.globals.update(level_label=level_label, CRITERION_PLAIN=CRITERION_PLAIN, CRITERION_LABEL=CRITERION_LABEL,
                   SUPPORT_LABEL=SUPPORT_LABEL, SupportType=SupportType, Criterion=Criterion,
                   count_chars=count_chars)

ROLE_LABEL = {"student": "학생", "teacher": "교사", "admin": "관리자"}
STATUS_LABEL = {"todo": "시작 전", "active": "진행 중", "paused": "잠시 멈춤", "done": "완료"}
KIND_TAG = {"direction": "생각해 볼 질문", "explanation": "설명", "demo": "시범 (다른 글)",
            "guide": "과제 안내", "vocab": "어휘 뜻", "structure": "비교표", "confirm": "확인 질문",
            "redirect": "다시 과제로", "done": "해냈어요", "ack": "자기검토"}
STUDENT_TAG = {"question": "질문", "answer_request": "요청"}
env.globals.update(ROLE_LABEL=ROLE_LABEL, STATUS_LABEL=STATUS_LABEL, KIND_TAG=KIND_TAG, STUDENT_TAG=STUDENT_TAG)


class NeedLogin(Exception):
    pass


class Forbidden(Exception):
    pass


@app.exception_handler(NeedLogin)
async def _need_login(request: Request, exc: NeedLogin):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(Forbidden)
async def _forbidden(request: Request, exc: Forbidden):
    return render(request, "message.html", title="접근 권한이 없어요",
                  body="이 화면은 교사·운영자만 볼 수 있어요.", status_code=403)


# ---------- 공통 ----------
def current_user(request: Request) -> dict | None:
    return request.session.get("user")


class NeedPassword(Exception):
    pass


@app.exception_handler(NeedPassword)
async def _need_password(request: Request, exc: NeedPassword):
    return RedirectResponse("/account/password", status_code=303)


class NeedProfile(Exception):
    pass


@app.exception_handler(NeedProfile)
async def _need_profile(request: Request, exc: NeedProfile):
    return RedirectResponse("/welcome", status_code=303)


def require(request: Request, *roles: str, allow_must_change: bool = False) -> dict:
    user = current_user(request)
    if not user:
        raise NeedLogin()
    from web.accounts import recheck

    user = recheck(request, user)
    if not user:
        raise NeedLogin()
    if user.get("must_change") and not allow_must_change:
        raise NeedPassword()
    if user.get("needs_profile") and request.url.path != "/welcome":
        raise NeedProfile()
    if roles and user["role"] not in roles and user["role"] != "admin":
        raise Forbidden()
    return user


def engine_for(user: dict, student_id: str | None = None) -> Engine:
    store = get_store()
    state = store.load(student_id or user["id"])
    return Engine(state, get_analyzer(demo=bool(user.get("is_demo"))), suspended=set(store.suspended()))


def save(eng: Engine, user: dict) -> None:
    get_store().save(eng.state, is_demo=bool(user.get("is_demo")), name=user.get("name", ""))


def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx.setdefault("user", current_user(request))
    ctx.setdefault("path", request.url.path)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> Response:
    return RedirectResponse(url, status_code=303)


# ---------- 인증 ----------
@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True, "store": type(get_store()).__name__, "content": active_version()})


@app.get("/")
def index(request: Request):
    user = current_user(request)
    if not user:
        return redirect("/login")
    return redirect("/mvp" if user["role"] in ("student", "admin") else "/teacher/mvp")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if current_user(request):
        return redirect("/")
    return render(request, "login.html", settings=settings, error=None)


@app.post("/login")
def login(request: Request, login_id: str = Form(""), password: str = Form("")):
    s = settings
    if s.test_login_enabled and hmac.compare_digest(login_id.strip(), s.test_login_id) \
            and hmac.compare_digest(password, s.test_login_password):
        # 브라우저마다 별도 데모 학습자 → 공개 사이트에서 방문자끼리 기록이 섞이지 않음
        demo_id = request.session.get("demo_id") or f"demo-{secrets.token_hex(8)}"
        request.session["demo_id"] = demo_id
        request.session["user"] = {"id": demo_id, "name": "테스트 사용자", "role": "admin", "is_demo": True}
        return redirect("/mvp")
    from web.accounts import authenticate

    try:                                    # 아이디 계정 (관리자·교사가 발급). 이메일은 /login/code
        user, err = authenticate(login_id, password)
    except RuntimeError:
        user, err = None, "로그인 서버에 연결하지 못했어요. 잠시 뒤 다시 해 주세요."
    if user:
        demo_id = request.session.get("demo_id")
        request.session.clear()
        if demo_id:
            request.session["demo_id"] = demo_id
        request.session["user"] = user
        return redirect("/account/password" if user["must_change"] else "/")
    return render(request, "login.html", settings=s, status_code=401, error=err)


@app.post("/logout")
def logout(request: Request):
    demo_id = request.session.get("demo_id")
    request.session.clear()
    if demo_id:
        request.session["demo_id"] = demo_id     # 같은 브라우저로 다시 들어오면 이어서
    return redirect("/login")


# ---------- 학생: 홈 ----------
@app.get("/home", response_class=HTMLResponse)
def home(request: Request):
    user = require(request, "student")
    eng = engine_for(user)
    pack = eng.pack()
    topics = pack.topics()
    status = {t.id: eng.topic_status(t.id) for t in topics}
    current = next((t for t in topics if status[t.id] in ("active", "paused")), None) \
        or next((t for t in topics if status[t.id] == "todo"), None)
    strong = [c for c in Criterion if (getattr(eng.state.criteria.get(c.value), "level", None) or 0) >= 2]
    supps = [(s, pack.bundles[s.bundle_id]) for s in eng.state.sessions.values()
             if s.bundle_id in pack.bundles and pack.bundles[s.bundle_id].kind == "supplement"
             and s.status != "done"]
    return render(request, "home.html", topics=topics, status=status, current=current, strong=strong,
                  entry=eng.latest_entry(), supps=supps, done_n=sum(v == "done" for v in status.values()))


# ---------- 학생: 수업 ----------
def lesson_context(eng: Engine, session) -> dict:
    bundle = eng.bundle(session)
    pack = eng.pack(session)
    ctx = {"bundle": bundle, "session": session, "pack": pack}
    if session.status == "done":
        done_msgs = [m.text for ss in session.steps.values() for m in ss.messages
                     if m.kind == "done" and "기록해 두" not in m.text]
        ctx.update(done_msgs=list(dict.fromkeys(done_msgs)),
                   partial=any(s.status == "done" and (s.level is None or s.level < 3)
                               for s in session.steps.values()),
                   next_bundle=pack.bundles.get(bundle.next) if bundle.next and bundle.kind == "topic" else None,
                   all_done=eng.all_topics_done())
        return ctx
    step = eng.current_step(session)
    ss = eng.step_state(session)
    real = answered(ss)
    dots = []
    for i, s in enumerate(bundle.steps):
        st_ = session.steps.get(s.id)
        dots.append("current" if i == session.step_idx else
                    (st_.status if st_ and st_.status in ("done", "skipped") else "todo"))
    dialog = step.kind in ("task", "judge")
    check = step.independent_check or step.allow_one_direction
    opening = None
    if dialog:
        opening = ("새 글이에요. 이번에는 혼자 해 보는 확인이라 내용 힌트 없이 진행해요. 제시문을 읽고 답해 보세요."
                   if check else
                   "제시문을 읽고 위 과제에 답해 보세요. 답이 아니어도 괜찮아요. 낱말 뜻이나 과제가 궁금하면 물어봐요. "
                   "정답은 먼저 알려 주지 않지만, 내 답을 보고 함께 생각해 볼게요.")
    preface = None
    if not ss.messages:
        for prev in reversed(bundle.steps[:session.step_idx]):
            pst = session.steps.get(prev.id)
            if pst and pst.status == "done":
                dm = [m.text for m in pst.messages if m.kind == "done"]
                preface = dm[-1] if dm else None
                break
    ctx.update(step=step, ss=ss, dots=dots, dialog=dialog, check=check, opening=opening, preface=preface,
               passages=[pack.excerpts[e] for e in step.excerpts if e not in eng.suspended],
               blocked=[e for e in step.excerpts if e in eng.suspended],
               carried=eng.carry(session, step), help_options=eng.help_options(session),
               default=session.outputs.get(step.id) or (real[-1].text if real else ""),
               prev_choice=real[-1].choice if real else None,
               prev_evidence=real[-1].evidence if real else "",
               intro=bundle.intro if session.step_idx == 0 and not ss.attempts else None)
    return ctx


def _lesson_response(request: Request, eng: Engine, session, error: str | None = None):
    tpl = "_lesson.html" if request.headers.get("HX-Request") else "lesson.html"
    return render(request, tpl, error=error, **lesson_context(eng, session))


@app.get("/learn/{bundle_id}", response_class=HTMLResponse)
def lesson(request: Request, bundle_id: str):
    user = require(request, "student")
    eng = engine_for(user)
    if bundle_id not in eng.pack().bundles:
        return render(request, "message.html", title="없는 학습이에요", body="", status_code=404)
    try:
        session = eng.start(bundle_id)
    except LearningError as e:
        return render(request, "message.html", title="지금은 진행할 수 없어요", body=str(e), status_code=409)
    save(eng, user)
    return render(request, "lesson.html", error=None, **lesson_context(eng, session))


@app.post("/learn/{bundle_id}/submit", response_class=HTMLResponse)
def lesson_submit(request: Request, bundle_id: str, answer: str = Form(""), evidence: str = Form(""),
                  choice: str | None = Form(None)):
    user = require(request, "student")
    eng = engine_for(user)
    session = eng.state.sessions.get(bundle_id)
    if not session:
        return redirect(f"/learn/{bundle_id}")
    error = None
    try:
        eng.submit(session, answer, evidence, choice or None)
        save(eng, user)
    except LearningError as e:
        error = str(e)
    return _lesson_response(request, eng, session, error)


@app.post("/learn/{bundle_id}/help", response_class=HTMLResponse)
def lesson_help(request: Request, bundle_id: str, kind: str = Form(...), word: str | None = Form(None)):
    user = require(request, "student")
    eng = engine_for(user)
    session = eng.state.sessions.get(bundle_id)
    if not session:
        return redirect(f"/learn/{bundle_id}")
    error = None
    try:
        eng.request_help(session, kind, word)
        save(eng, user)
    except LearningError as e:
        error = str(e)
    return _lesson_response(request, eng, session, error)


@app.post("/learn/{bundle_id}/pause")
def lesson_pause(request: Request, bundle_id: str, answer: str = Form("")):
    user = require(request, "student")
    eng = engine_for(user)
    session = eng.state.sessions.get(bundle_id)
    if session and session.status != "done":
        eng.save_draft(session, answer)
        eng.pause(session)
        save(eng, user)
    resp = redirect("/home")
    if request.headers.get("HX-Request"):
        resp = Response(status_code=200, headers={"HX-Redirect": "/home"})
    return resp


# ---------- 학생: 결과 ----------
RESULT_TITLE = {
    EntryDecision.READY: "본격 학습을 시작할 준비가 되었어요",
    EntryDecision.CONDITIONAL: "본격 학습을 시작할 수 있어요",
    EntryDecision.SUPPLEMENT: "짧은 보충 후 다시 확인해요",
    EntryDecision.HOLD: "한 번 더 확인이 필요해요",
}


@app.get("/result", response_class=HTMLResponse)
def result(request: Request, sent: int = 0):
    user = require(request, "student")
    eng = engine_for(user)
    pack = eng.pack()
    entry = eng.latest_entry()
    if not entry:
        left = [t for t in pack.topics() if eng.topic_status(t.id) != "done"]
        return render(request, "result.html", entry=None, left=left)
    decision = EntryDecision(entry["decision"])
    levels = entry["levels"]
    can = [c for c in Criterion if (levels.get(c.value) if levels.get(c.value) is not None else -1) >= 2]
    need = [c for c in Criterion if c not in can]
    recs = [(r, pack.review_items.get(r.item)) for r in eng.state.reviews if r.action == "recommended"]
    return render(request, "result.html", entry=entry, decision=decision, levels=levels, can=can, need=need,
                  title=RESULT_TITLE[decision], message=STUDENT_MESSAGE[decision], ED=EntryDecision,
                  supps=eng.supplement_options() if decision == EntryDecision.SUPPLEMENT else [],
                  recs=[x for x in recs if x[1]], criteria=eng.state.criteria, sent=sent,
                  focus=[Criterion(c) for c in entry["focus"]])


@app.post("/result/dispute")
def result_dispute(request: Request, criterion: str = Form(...), why: str = Form("")):
    user = require(request, "student")
    eng = engine_for(user)
    if criterion in {c.value for c in Criterion}:
        eng.dispute(criterion, why.strip()[:500] or "학생이 재확인을 요청함")
        save(eng, user)
    return redirect("/result?sent=1")


# ---------- 학생: 선택 복습 ----------
@app.get("/review", response_class=HTMLResponse)
def review(request: Request, item: str | None = None):
    user = require(request, "student")
    eng = engine_for(user)
    pack = eng.pack()
    recommended = {}
    for r in eng.state.reviews:
        if r.action == "recommended":
            recommended.setdefault(r.item, r.reason)
    topic_names = {t.id: t.title for t in pack.topics()}
    if item and item in pack.review_items:
        eng.state.reviews.append(ReviewRecord(item=item, action="opened", reason="학생이 선택"))
        save(eng, user)
        return render(request, "review_item.html", item=pack.review_items[item], topic_names=topic_names)
    items = sorted(pack.review_items.values(),
                   key=lambda i: (i.id not in recommended, i.topic, [int(x) for x in i.id.split("-")]))
    return render(request, "review.html", items=items, recommended=recommended, topic_names=topic_names)


@app.post("/review/{item}/{action}")
def review_action(request: Request, item: str, action: str, text: str = Form("")):
    user = require(request, "student")
    eng = engine_for(user)
    if item in eng.pack().review_items and action in ("saved", "practiced"):
        eng.state.reviews.append(ReviewRecord(item=item, action=action,
                                              reason=text.strip()[:200] or "나중에 보기"))
        save(eng, user)
    return redirect(f"/review?item={item}" if action == "practiced" else "/review")


# ---------- 교사: 학습 기록 ----------
@app.get("/teacher/records", response_class=HTMLResponse)
def records(request: Request, student: str | None = None, tab: str = "criteria"):
    user = require(request, "teacher")
    from web.accounts import visible_students

    students = visible_students(user)       # 교사: 자기 학급 / 관리자: 전체 / 데모: 자기 기록
    sid = student if student in {s["id"] for s in students} else (students[0]["id"] if students else None)
    if not sid:
        return render(request, "records.html", students=[], sid=None, tab=tab)
    eng = engine_for(user, sid)
    pack = eng.pack()
    return render(request, "records.html", students=students, sid=sid, tab=tab, state=eng.state, pack=pack,
                  entry=eng.latest_entry(),
                  done_n=sum(eng.topic_status(t.id) == "done" for t in pack.topics()),
                  open_flags=[f for f in eng.state.flags if not f.resolved])


@app.post("/teacher/records/override")
def records_override(request: Request, student: str = Form(...), criterion: str = Form(...),
                     level: str = Form(...), note: str = Form("")):
    user = require(request, "teacher")
    from web.accounts import can_see

    if not can_see(user, student):
        raise Forbidden()
    if not note.strip() or criterion not in {c.value for c in Criterion}:
        return redirect(f"/teacher/records?student={student}")
    eng = engine_for(user, student)
    eng.teacher_set(criterion, None if level == "none" else int(level), note.strip()[:300], user["name"])
    get_store().save(eng.state, is_demo=student.startswith("demo-"), name="")
    return redirect(f"/teacher/records?student={student}")


@app.post("/teacher/records/flag")
def records_flag(request: Request, student: str = Form(...), index: int = Form(...)):
    user = require(request, "teacher")
    from web.accounts import can_see

    if not can_see(user, student):
        raise Forbidden()
    eng = engine_for(user, student)
    if 0 <= index < len(eng.state.flags):
        f = eng.state.flags[index]
        f.resolved = True
        eng.state.log("flag_resolved", f.source, kind=f.kind, by=user["name"])
        get_store().save(eng.state, is_demo=student.startswith("demo-"), name="")
    return redirect(f"/teacher/records?student={student}&tab=flags")


# ---------- 교사: 자료 관리 ----------
@app.get("/teacher/content", response_class=HTMLResponse)
def content_admin(request: Request, version: str | None = None, tab: str = "bundles"):
    require(request, "teacher")
    versions = available_versions()
    ver = version if version in versions else active_version()
    pack = load_pack(ver)
    used = {ex: [f"{b.id}/{s.id}" for b in pack.bundles.values() for s in b.steps
                 if ex in s.excerpts or (s.demo and s.demo.excerpt == ex)] for ex in pack.excerpts}
    return render(request, "content.html", pack=pack, versions=versions, ver=ver, active=active_version(),
                  suspended=get_store().suspended(), used=used, tab=tab)


@app.post("/teacher/content/status")
def content_status(request: Request, item: str = Form(...), status: str = Form(...), note: str = Form("")):
    user = require(request, "teacher")
    if user.get("is_demo"):
        return render(request, "message.html", title="테스트 계정에서는 바꿀 수 없어요",
                      body="자료 사용 중지는 모든 학생에게 적용되므로 정식 교사 계정에서만 할 수 있어요.", status_code=403)
    if status in ("approved", "suspended") and (status == "approved" or note.strip()):
        get_store().set_status(item, status, note.strip()[:200], user["name"])
    return redirect("/teacher/content")


# ---------- 교사: AI 품질 ----------
REPORTS = ROOT / "evals" / "reports"
REPORT_NAMES = {"latest_llm.json": "최신 · 실제 AI 분석기", "latest_demo.json": "최신 · 데모 분석기",
                "baseline_demo.json": "기준선 · 데모 분석기"}


@app.get("/teacher/quality", response_class=HTMLResponse)
def quality(request: Request, report: str | None = None, all_cases: int = 0):
    require(request, "teacher")
    from evals.report import LABEL

    files = sorted(REPORTS.glob("*.json"), key=lambda p: (p.name not in REPORT_NAMES,
                                                         list(REPORT_NAMES).index(p.name)
                                                         if p.name in REPORT_NAMES else 0))
    if not files:
        return render(request, "quality.html", rep=None, files=[], names=REPORT_NAMES)
    f = next((p for p in files if p.name == report), files[0])
    rep = json.loads(f.read_text(encoding="utf-8"))
    cases = [c for c in rep["cases"] if all_cases or not c["decision_correct"] or c["error_correct"] is False]
    return render(request, "quality.html", rep=rep, files=files, current=f.name, names=REPORT_NAMES,
                  LABEL=LABEL, cases=cases, all_cases=all_cases)


# ---------- 6단계 논술학습 MVP ----------
from web import accounts as _accounts  # noqa: E402  (헬퍼 정의 뒤에 불러와야 순환 참조가 풀린다)
from web import email_auth as _email_auth  # noqa: E402
from web import mvp as _mvp  # noqa: E402

app.include_router(_mvp.router)
app.include_router(_accounts.router)
app.include_router(_email_auth.router)


# 로컬 실행 시에만 public/ 을 직접 제공 (Vercel 에서는 CDN 이 제공하므로 마운트하지 않음)
if not ON_VERCEL:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=ROOT / "public"), name="public")
