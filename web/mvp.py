"""6단계 논술학습 MVP 화면 (가이드 10·11·12장).

학생: 처음 안내 → 학습 홈 → 단계 화면(0~5 문답, 6 원고지, 6-1 첨삭) → 돌아보기 → 나의 기록
교사: 학급 현황·검토 대기열 → 학생 상세(타임라인·사고 변화·답안·평가) → 의견 집계
공개 범위: 학생 화면으로 가는 템플릿 컨텍스트에는 pack.view_student() 범위와 학생 본인 기록만 넣는다.
"""
import difflib
import html
import json
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from markupsafe import Markup

import web.main as _main
from src.mvp import ai as roles_mod
from src.mvp.engine import MvpEngine, MvpError, circled, score_rows
from src.mvp.pack import guide_pages, reflection_items, stage_cards
from src.mvp.text import GUIDE_CELL, MAX_CELLS, cells_used, official_count
from web.main import Forbidden, env, redirect, render, require

router = APIRouter()

SUPPORT_KO = {"independent": "독립 수행", "question_then_revised": "질문 후 수정", "scaffolded": "발판 후 수행",
              "explained_then_restated": "해설 후 재서술"}
STAGE_STATUS_KO = {"locked": "잠김", "in_progress": "진행 중", "summarizing": "정리 중", "judging": "판정 중",
                   "completed": "완료", "flagged": "선생님 확인 중"}
DRAFT_KO = {"independent": "① 독립 초고", "selfchecked": "② 자기검증", "pre_revision": "③ 선행 수정본",
            "submitted": "④ 첨삭 전 제출본", "final": "첨삭 후 최종본"}
ANN_STATUS_KO = {"active": "검토 중", "withdrawn": "철회됨", "adjusted": "조정됨", "resolved": "해결", "unresolved": "미해결"}
NATURE_KO = {"correction": "오류 교정", "optional_improvement": "선택적 개선", "strength": "유지할 강점"}
DECISION_KO = {"accept": "수용", "partial": "부분 수용", "reject": "비수용"}
SELFCHECK_KO = {"found_and_fixed": "독립 발견·수정", "checked_and_kept": "독립 점검·유지",
                "found_unresolved": "발견했으나 미해결", "insufficient_check": "점검 불충분"}
ALERT_KO = {"stall": "정체", "grading_mismatch": "채점 불일치", "paste": "붙여넣기", "ai_copy": "튜터 예시 유사",
            "danger": "위험 신호", "appeal": "이의 제기", "unresolved": "미해결 첨삭"}
ALERT_STATUS_KO = {"received": "접수", "reviewing": "검토 중", "done": "조치 완료", "held": "보류"}
CONDITION_KO = {"independent_after_support": "지원 후 독립 작성", "ai_supported": "튜터 지원", "teacher_supported": "교사 지원",
                "interrupted_then_supplemented": "중단 후 보충"}
ISSUE_KO = {"keyword_only": "낱말만 말함", "case_as_claim": "사례를 주장으로 착각", "overclaim": "원문보다 강한 단정",
            "background_knowledge": "제시문 밖 지식", "false_identity": "다른 것을 같다고 봄",
            "false_dichotomy": "대립·양자택일로 봄", "not_linked_to_task": "논제와 연결 안 됨"}
INTENT_KO = {"answer_request": "정답 요구", "off_task": "과제 이탈", "dont_know": "모르겠어요", "disagree": "반대 의견",
             "danger": "위험 신호"}
SUBGOAL_KO = {"met": "충족", "partial": "부분", "not_yet": "아직", "skipped": "건너뜀"}
REVIEW_STEPS = [("diagnose", "① 제출본 인계 · ② 짧은 자기진단"), ("results", "③ 평가 공개 (강점 먼저)"),
                ("threads", "④ 첨삭 과제 선택 · ⑤ 원고 연결 문답 · ⑥ 수용 판단"), ("revise", "⑦ 수정본 작성"),
                ("compare", "⑧ 재평가 전후 비교"), ("done", "⑨ 다음 점검 질문 · 돌아보기")]
WRITE_STEPS = ["① 독립 초고", "② 자기검증", "③ 선행 수정본", "④ 제출 (고정)"]
env.globals.update(ISSUE_KO=ISSUE_KO, INTENT_KO=INTENT_KO, SUBGOAL_KO=SUBGOAL_KO, REVIEW_STEPS=REVIEW_STEPS,
                   WRITE_STEPS=WRITE_STEPS)
env.globals.update(SUPPORT_KO=SUPPORT_KO, STAGE_STATUS_KO=STAGE_STATUS_KO, DRAFT_KO=DRAFT_KO,
                   ANN_STATUS_KO=ANN_STATUS_KO, NATURE_KO=NATURE_KO, DECISION_KO=DECISION_KO,
                   SELFCHECK_KO=SELFCHECK_KO, ALERT_KO=ALERT_KO, ALERT_STATUS_KO=ALERT_STATUS_KO,
                   CONDITION_KO=CONDITION_KO, circled=circled, MAX_CELLS=MAX_CELLS, GUIDE_CELL=GUIDE_CELL)


# ---------------------------------------------------------------- 마크다운 (안내 문안)
def _inline(s: str) -> str:
    s = html.escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def md(text: str) -> Markup:
    out, lst, table = [], None, []

    def flush():
        nonlocal lst, table
        if lst:
            out.append(f"<{lst[0]}>" + "".join(f"<li>{x}</li>" for x in lst[1]) + f"</{lst[0]}>")
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|?[\s:\-|]+\|?", r)]
            cells = [[_inline(c.strip()) for c in r.strip("|").split("|")] for r in rows]
            head = "".join(f"<th>{c}</th>" for c in cells[0])
            body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f'<div class="scroll-x"><table class="tbl"><tr>{head}</tr>{body}</table></div>')
        lst, table = None, []

    for line in text.splitlines():
        t = line.strip()
        if t.startswith("|"):
            if lst:
                flush()
            table.append(t)
            continue
        if table:
            flush()
        if m := re.match(r"^(#{1,3})\s+(.*)", t):
            flush()
            n = len(m.group(1)) + 1
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif m := re.match(r"^[-*]\s+(.*)", t):
            if not lst or lst[0] != "ul":
                flush()
                lst = ("ul", [])
            lst[1].append(_inline(m.group(1)))
        elif m := re.match(r"^\d+\.\s+(.*)", t):
            if not lst or lst[0] != "ol":
                flush()
                lst = ("ol", [])
            lst[1].append(_inline(m.group(1)))
        elif t:
            flush()
            out.append(f"<p>{_inline(t)}</p>")
        else:
            flush()
    flush()
    return Markup("".join(out))


env.filters["md"] = md


def marked_body(body: str, anns: list, active: int | None = None) -> Markup:
    """고정본 본문에 첨삭 표시를 그린다 (번호 + 항목명 + 성격 라벨, 색만으로 구분하지 않음)."""
    spans = sorted([a for a in anns if a.shown and a.status not in ("withdrawn",)],
                   key=lambda a: (a.anchor.get("start", 0), -a.anchor.get("end", 0)))
    out, pos = [], 0
    for a in spans:
        s, e = a.anchor.get("start", 0), a.anchor.get("end", 0)
        if s < pos:
            continue
        out.append(html.escape(body[pos:s]))
        num = f'<a class="ann-num" href="#ann-{a.number}" data-ann="{a.number}">{circled(a.number)}</a>'
        cls = f"ann ann-{a.nature} ann-{a.mark_type}" + (" on" if a.number == active else "")
        if e > s:
            out.append(f'<mark class="{cls}" id="mark-{a.number}">{html.escape(body[s:e])}</mark>{num}')
        else:
            out.append(f'<span class="{cls}" id="mark-{a.number}">∨</span>{num}')
        pos = e if e > s else pos
    out.append(html.escape(body[pos:]))
    paras = "".join(f"<p>{p}</p>" for p in "".join(out).split("\n") if p.strip())
    return Markup(paras)


def diff_html(a: str, b: str) -> Markup:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(html.escape(a[i1:i2]))
        if op in ("delete", "replace"):
            out.append(f"<del>{html.escape(a[i1:i2])}</del>")
        if op in ("insert", "replace"):
            out.append(f"<ins>{html.escape(b[j1:j2])}</ins>")
    return Markup("".join(out).replace("\n", "<br>"))


env.globals.update(marked_body=marked_body, diff_html=diff_html)


# ---------------------------------------------------------------- 공통
def _store():
    return _main.get_store()        # 테스트에서 web.main.get_store 를 바꿔 끼울 수 있게 모듈 경유


def _demo(user: dict) -> bool:
    return bool(user.get("is_demo"))


def load(user: dict, sid: str | None = None) -> MvpEngine:
    state = _store().load(sid or user["id"])
    return MvpEngine(state, roles_mod.get_roles(demo=_demo(user)))


def persist(eng: MvpEngine, user: dict, sid: str | None = None) -> None:
    eng.save()
    is_demo = (sid or user["id"]).startswith("demo-")
    _store().save(eng.state, is_demo=is_demo, name="" if sid else user.get("name", ""))


def stage_href(sid: str) -> str:
    return f"/mvp/stage/{sid}"


def progress(eng: MvpEngine) -> list[dict]:
    a = eng.attempt
    return [{"id": s.id, "name": s.name, "status": a.stages[s.id].status, "current": s.id == a.current}
            for s in eng.cards.stages]


def base_ctx(eng: MvpEngine) -> dict:
    return {"att": eng.attempt, "cards": eng.cards, "exam": eng.pack.view_student()["exam"],
            "steps": progress(eng), "limits": eng.pack.meta["limits"]}


# ---------------------------------------------------------------- 학생: 안내·홈
@router.get("/mvp", response_class=HTMLResponse)
def mvp_home(request: Request):
    user = require(request, "student")
    eng = load(user)
    no_class = user["role"] == "student" and not _demo(user) and not _store().classes_of_student(user["id"])
    if not eng.attempt:
        return render(request, "mvp_home.html", att=None, pack_title="기본과정 출제 문제 1", no_class=no_class)
    if not eng.attempt.onboarded:
        return redirect("/mvp/guide?first=1")
    a = eng.attempt
    card = eng.cards.get(a.current)
    prev_q = next((x.get("next_check_question") for x in eng.state.mvp.values()
                   if x.get("next_check_question") and x["id"] != a.id), "")
    return render(request, "mvp_home.html", **base_ctx(eng), card=card, recap=eng.recap(),
                  next_q=a.next_check_question or prev_q, changes=_changes(), no_class=no_class)


def _changes() -> str:
    from src.mvp.pack import ROOT
    p = ROOT / "changes.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


@router.post("/mvp/start")
def mvp_start(request: Request):
    user = require(request, "student")
    eng = load(user)
    if not eng.attempt or eng.attempt.status == "done":
        eng.start()
        persist(eng, user)
    return redirect("/mvp")


@router.get("/mvp/guide", response_class=HTMLResponse)
def mvp_guide(request: Request, first: int = 0, page: int = 0):
    require(request)
    pages = guide_pages()
    page = max(0, min(page, len(pages) - 1))
    return render(request, "mvp_guide.html", pages=pages, page=page, first=first)


@router.post("/mvp/guide/done")
def mvp_guide_done(request: Request):
    user = require(request, "student")
    eng = load(user)
    if eng.attempt:
        eng.attempt.onboarded = True
        persist(eng, user)
    return redirect("/mvp")


# ---------------------------------------------------------------- 학생: 0~5단계 문답
def _stage_ctx(eng: MvpEngine, sid: str, error: str | None = None) -> dict:
    a = eng.attempt
    r = a.stages[sid]
    card = eng.cards.get(sid)
    cands = eng.summary_candidates() if r.status in ("summarizing", "in_progress") and a.current == sid else {}
    sg = card.subgoals[r.subgoal_idx] if r.subgoal_idx < len(card.subgoals) else None
    return {**base_ctx(eng), "card": card, "run": r, "subgoal": sg, "cands": cands, "error": error,
            "prior": eng.prior_outputs(sid), "recap": eng.recap() if a.current == sid else "",
            "readonly": a.current != sid}


@router.get("/mvp/stage/{sid}", response_class=HTMLResponse)
def mvp_stage(request: Request, sid: str):
    user = require(request, "student")
    eng = load(user)
    a = eng.attempt
    if not a or sid not in a.stages:
        return redirect("/mvp")
    if a.stages[sid].status == "locked":
        return redirect(stage_href(a.current))
    card = eng.cards.get(sid)
    if card.kind == "writing":
        return mvp_write(request)
    if card.kind == "review":
        return mvp_review(request)
    return render(request, "mvp_stage.html", **_stage_ctx(eng, sid))


def _partial_or_page(request: Request, eng: MvpEngine, sid: str, error: str | None = None) -> Response:
    if request.headers.get("HX-Request"):
        return render(request, "_mvp_dialogue.html", **_stage_ctx(eng, sid, error))
    return render(request, "mvp_stage.html", **_stage_ctx(eng, sid, error)) if error else redirect(stage_href(sid))


@router.post("/mvp/stage/{sid}/say")
def mvp_say(request: Request, sid: str, text: str = Form("")):
    user = require(request, "student")
    eng = load(user)
    if not eng.attempt or eng.attempt.current != sid:
        return redirect("/mvp")
    try:
        eng.student_turn(text)
    except MvpError as e:
        return _partial_or_page(request, eng, sid, str(e))
    persist(eng, user)
    return _partial_or_page(request, eng, sid)


@router.post("/mvp/stage/{sid}/skip")
def mvp_skip(request: Request, sid: str):
    user = require(request, "student")
    eng = load(user)
    try:
        if eng.attempt and eng.attempt.current == sid:
            eng.skip_subgoal()
            persist(eng, user)
    except MvpError as e:
        return _partial_or_page(request, eng, sid, str(e))
    return _partial_or_page(request, eng, sid)


@router.post("/mvp/stage/{sid}/summary")
async def mvp_summary(request: Request, sid: str):
    user = require(request, "student")
    eng = load(user)
    if not eng.attempt or eng.attempt.current != sid:
        return redirect("/mvp")
    form = await request.form()
    fields = {f.key: str(form.get(f"f_{f.key}", "")) for f in eng.cards.get(sid).outputs}
    try:
        out = eng.submit_summary(fields)
    except MvpError as e:
        return render(request, "mvp_stage.html", **_stage_ctx(eng, sid, str(e)))
    persist(eng, user)
    if out.verdict == "pass":
        return redirect(stage_href(eng.attempt.current))
    return redirect(stage_href(sid))


# ---------------------------------------------------------------- 학생: 6단계 원고지
@router.get("/mvp/write", response_class=HTMLResponse)
def mvp_write(request: Request):
    user = require(request, "student")
    eng = load(user)
    a = eng.attempt
    if not a or a.stages["6"].status == "locked":
        return redirect("/mvp")
    return render(request, "mvp_write.html", **base_ctx(eng), card=eng.cards.get("6"),
                  outline=eng.prior_outputs("6"), body=a.temp_draft, ind=a.draft("independent"),
                  pre=a.draft("pre_revision"), sub=a.draft("submitted"), sc=a.selfcheck,
                  chars=official_count(a.temp_draft), cells=cells_used(a.temp_draft),
                  dialogue_stages=[s for s in eng.cards.stages if s.kind == "dialogue"])


@router.post("/mvp/write/autosave")
async def mvp_autosave(request: Request):
    user = require(request, "student")
    eng = load(user)
    data = await request.json()
    try:
        info = eng.autosave(str(data.get("body", "")), [int(x) for x in data.get("pastes", [])][:20],
                            bool(data.get("a11y")))
    except MvpError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    persist(eng, user)
    return JSONResponse({"ok": True, **info})


@router.post("/mvp/write/{action}")
async def mvp_write_action(request: Request, action: str):
    user = require(request, "student")
    eng = load(user)
    form = await request.form()
    msg = None
    try:
        if "body" in form and action in ("draft", "pre_revision"):
            eng.autosave(str(form["body"]))
        if action == "draft":
            eng.complete_draft()
        elif action == "selfcheck":
            entries = [{"key": c.key, "judgment": form.get(f"j_{c.key}"), "quote": form.get(f"q_{c.key}", ""),
                        "reason": form.get(f"r_{c.key}", "")} for c in eng.cards.get("6").selfcheck]
            eng.submit_selfcheck(entries, str(form.get("confident", "")), str(form.get("uncertain", "")))
        elif action == "pre_revision":
            eng.save_pre_revision(str(form.get("body", "")))
        elif action == "submit":
            eng.submit()
            persist(eng, user)
            return redirect(stage_href("6.1"))
        elif action == "help":
            msg = eng.help_request(str(form.get("question", "")))
        elif action == "interrupt":
            eng.interrupt(str(form.get("target", "")), str(form.get("reason", "")))
            persist(eng, user)
            return redirect(stage_href(eng.attempt.current))
        else:
            return redirect("/mvp/write")
    except MvpError as e:
        a = eng.attempt
        return render(request, "mvp_write.html", **base_ctx(eng), card=eng.cards.get("6"),
                      outline=eng.prior_outputs("6"), body=str(form.get("body", a.temp_draft)),
                      ind=a.draft("independent"), pre=a.draft("pre_revision"), sub=a.draft("submitted"),
                      sc=a.selfcheck, chars=official_count(a.temp_draft), cells=cells_used(a.temp_draft),
                      dialogue_stages=[s for s in eng.cards.stages if s.kind == "dialogue"], error=str(e),
                      form=form)
    persist(eng, user)
    if msg:
        return render(request, "message.html", title="도움 요청", body=msg, back="/mvp/write")
    return redirect("/mvp/write")


# ---------------------------------------------------------------- 학생: 6-1 평가·첨삭
def _review_ctx(eng: MvpEngine, sel: int | None = None, error: str | None = None) -> dict:
    a = eng.attempt
    sub = a.draft("submitted")
    fin = a.draft("final")
    ev_sub = a.latest_eval(sub.id) if sub else None
    ev_fin = a.latest_eval(fin.id) if fin else None
    show = a.review_phase not in ("diagnose",)      # 본인 채점 결과는 자기진단 이후 공개 (12장)
    anns = [x for x in a.annotations]
    sel = sel or next((x.number for x in anns if x.shown and x.nature != "strength"), None)
    return {**base_ctx(eng), "sub": sub, "fin": fin, "ev_sub": ev_sub if show else None,
            "ev_fin": ev_fin, "rows_sub": score_rows(eng.rubric, ev_sub) if (show and ev_sub) else [],
            "rows_fin": score_rows(eng.rubric, ev_fin) if ev_fin else [], "rubric": eng.rubric,
            "anns": anns if a.review_phase not in ("diagnose", "results") else [x for x in anns if x.nature == "strength"],
            "sel": sel, "phase": a.review_phase, "error": error, "sc": a.selfcheck,
            "tasks_hint": ["(가) 관점 설명", "(나) 관점 설명", "두 설명 비교", "기타"],
            "model_answers": eng.pack.model_answers if eng.model_answer_open() else [],
            "card": eng.cards.get("6.1")}


@router.get("/mvp/review", response_class=HTMLResponse)
def mvp_review(request: Request, sel: int | None = None):
    user = require(request, "student")
    eng = load(user)
    a = eng.attempt
    if not a or a.stages["6.1"].status == "locked":
        return redirect("/mvp")
    return render(request, "mvp_review.html", **_review_ctx(eng, sel))


@router.post("/mvp/review/{action}")
async def mvp_review_action(request: Request, action: str):
    user = require(request, "student")
    eng = load(user)
    form = await request.form()
    sel = int(form["number"]) if str(form.get("number", "")).isdigit() else None
    try:
        if action == "diagnose":
            pm = {k: str(form.get(k, "")) for k in ("p1", "p2", "p3")}
            eng.submit_diagnosis(str(form.get("confident", "")), str(form.get("uncertain", "")), pm)
        elif action == "threads":
            eng.to_threads()
        elif action == "reply":
            eng.thread_reply(sel, str(form.get("text", "")))
        elif action == "decide":
            eng.decide(sel, str(form.get("decision", "")), str(form.get("reason", "")), str(form.get("revision", "")))
        elif action == "appeal":
            eng.appeal(str(form.get("target", "")), str(form.get("reason", "")))
        elif action == "revise":
            eng.to_revise()
        elif action == "final":
            eng.submit_final(str(form.get("body", "")))
        elif action == "finish":
            eng.finish_review(str(form.get("next_question", "")))
            persist(eng, user)
            return redirect("/mvp/reflect")
    except MvpError as e:
        return render(request, "mvp_review.html", **_review_ctx(eng, sel, str(e)))
    persist(eng, user)
    return redirect("/mvp/review" + (f"?sel={sel}#thread" if sel else ""))


# ---------------------------------------------------------------- 학생: 돌아보기
@router.get("/mvp/reflect", response_class=HTMLResponse)
def mvp_reflect(request: Request, sent: int = 0):
    user = require(request, "student")
    eng = load(user)
    a = eng.attempt
    if not a or a.review_phase != "done":
        return redirect("/mvp")
    picks = [("제출본", s) for s in (a.draft("submitted").body.split("\n") if a.draft("submitted") else []) if s.strip()]
    picks += [("최종본", s) for s in (a.draft("final").body.split("\n") if a.draft("final") else []) if s.strip()]
    picks += [("사고 변화", f"{t.before} → {t.after}") for t in a.thinking]
    return render(request, "mvp_reflect.html", **base_ctx(eng), items=reflection_items()["items"],
                  ref=a.reflection, picks=picks, sent=sent)


@router.post("/mvp/reflect")
async def mvp_reflect_save(request: Request):
    user = require(request, "student")
    eng = load(user)
    form = await request.form()
    items = reflection_items()["items"]
    answers, feedback = {}, {}
    for it in items:
        if it["kind"] == "multi":
            v = [x for x in form.getlist(it["id"]) if x in it.get("options", [])][: it.get("max", 9)]
        else:
            v = str(form.get(it["id"], "")).strip()[:1000]
        if v:
            (answers if it["store"] == "personal" else feedback)[it["id"]] = v
    act = str(form.get("act", "draft"))
    try:
        eng.save_reflection(answers, submit=act == "submit", skip=act == "skip")
    except MvpError as e:
        return render(request, "message.html", title="돌아보기", body=str(e), status_code=400)
    persist(eng, user)
    if feedback and act != "skip" and str(form.get("fb_send", "")) == "1":
        named = str(form.get("fb_named", "")) == "1"
        _store().add_feedback("reflection_type1", feedback, user["id"] if named else None)
    return redirect("/mvp/reflect?sent=1" if act != "draft" else "/mvp/reflect")


# ---------------------------------------------------------------- 학생: 나의 기록
@router.get("/mvp/records", response_class=HTMLResponse)
def mvp_records(request: Request):
    user = require(request, "student")
    eng = load(user)
    atts = sorted(eng.state.mvp.values(), key=lambda x: x.get("started_at", ""), reverse=True)
    return render(request, "mvp_records.html", **(base_ctx(eng) if eng.attempt else {}), attempts=atts,
                  eng=eng)


@router.get("/mvp/records/download")
def mvp_download(request: Request):
    user = require(request, "student")
    eng = load(user)
    # 학생에게 내부 판단(지원 수준·불합격 초안 등)은 내려보내지 않는다
    out = []
    for a in eng.state.mvp.values():
        stages = {sid: {"status": r["status"], "outputs": r["outputs"],
                        "turns": [{"role": t["role"], "text": t["text"], "ts": t["ts"]} for t in r["turns"]]}
                  for sid, r in a["stages"].items()}
        out.append({"id": a["id"], "pack": f"{a['pack_id']}@{a['pack_version']}", "stages": stages,
                    "drafts": a["drafts"], "selfcheck": a["selfcheck"], "reflection": a["reflection"],
                    "next_check_question": a["next_check_question"]})
    return Response(json.dumps(out, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="elenchos-my-records.json"'})


# ---------------------------------------------------------------- 교사: 대시보드
def _students(user: dict) -> list[dict]:
    from web.accounts import visible_students
    return visible_students(user)


def _check_student(user: dict, sid: str) -> None:
    if sid not in {s["id"] for s in _students(user)}:
        raise Forbidden()


@router.get("/teacher/mvp", response_class=HTMLResponse)
def teacher_class(request: Request):
    user = require(request, "teacher")
    rows, queue = [], []
    for s in sorted(_students(user), key=lambda x: x.get("display_name") or x["id"]):   # 이름순 (서열표 금지)
        eng = load(user, s["id"])
        a = eng.attempt
        if not a:
            continue
        r = a.stages[a.current]
        dist = {}
        for run in a.stages.values():
            if run.status == "completed" and run.subgoals:
                dist[run.support] = dist.get(run.support, 0) + 1
        open_alerts = [(i, x) for i, x in enumerate(a.alerts) if x.status != "done"]
        rows.append({"s": s, "a": a, "card": eng.cards.get(a.current), "run": r, "dist": dist,
                     "alerts": open_alerts})
        queue += [(s, i, x) for i, x in open_alerts]
    queue.sort(key=lambda q: (q[2].kind != "danger", q[2].ts))
    return render(request, "mvp_teacher.html", rows=rows, queue=queue)


@router.get("/teacher/mvp/student/{sid}", response_class=HTMLResponse)
def teacher_student(request: Request, sid: str, tab: str = "timeline", stage: str | None = None):
    user = require(request, "teacher")
    _check_student(user, sid)
    eng = load(user, sid)
    if not eng.attempt:
        return render(request, "message.html", title="기록 없음", body="아직 6단계 학습을 시작하지 않았어요.")
    eng.audit(user.get("name", user["id"]), "view", tab)
    persist(eng, user, sid)
    a = eng.attempt
    evs = [(e, a.draft_by_id(e.draft_id), score_rows(eng.rubric, e)) for e in a.evaluations]
    ref = a.reflection
    return render(request, "mvp_teacher_student.html", sid=sid, att=a, cards=eng.cards, tab=tab,
                  open_stage=stage, evs=evs, rubric=eng.rubric, ref=ref,
                  steps=progress(eng), sub=a.draft("submitted"), fin=a.draft("final"))


@router.post("/teacher/mvp/student/{sid}/{action}")
async def teacher_action(request: Request, sid: str, action: str):
    user = require(request, "teacher")
    _check_student(user, sid)
    eng = load(user, sid)
    form = await request.form()
    who = user.get("name", user["id"])
    tab = "timeline"
    try:
        if action == "allow":
            eng.teacher_allow(str(form["stage"]), str(form["mode"]), who, str(form.get("note", "")))
        elif action == "regrade":
            lv = str(form.get("level", ""))
            eng.teacher_regrade(str(form["eval_id"]), str(form["code"]), None if lv == "none" else int(lv),
                                str(form.get("reason", "")), who)
            tab = "eval"
        elif action == "alert":
            eng.teacher_alert(int(form["idx"]), str(form["status"]), str(form.get("note", "")), who)
            tab = "alerts"
        elif action == "note":
            eng.teacher_note(str(form.get("text", "")), who)
            tab = "thinking"
    except (MvpError, KeyError, ValueError) as e:
        return render(request, "message.html", title="처리할 수 없어요", body=str(e), status_code=400)
    persist(eng, user, sid)
    return redirect(f"/teacher/mvp/student/{sid}?tab={tab}")


@router.get("/teacher/mvp/feedback", response_class=HTMLResponse)
def teacher_feedback(request: Request):
    user = require(request, "teacher")
    fb = _store().list_feedback()
    if _demo(user):
        fb = []              # 데모 관리자는 다른 방문자의 의견을 보지 않는다
    items = [i for i in reflection_items()["items"] if i["store"] == "feedback"]
    agg = {}
    for it in items:
        if it["kind"] in ("single", "multi"):
            cnt = {o: 0 for o in it["options"]}
            for f in fb:
                v = f["answers"].get(it["id"])
                for x in (v if isinstance(v, list) else [v] if v else []):
                    if x in cnt:
                        cnt[x] += 1
            agg[it["id"]] = cnt
    texts = [f["answers"].get("A8") for f in fb if f["answers"].get("A8")]
    return render(request, "mvp_feedback.html", items=items, agg=agg, n=len(fb), texts=texts,
                  show_agg=len(fb) >= 5)


@router.get("/teacher/mvp/guide", response_class=HTMLResponse)
def teacher_guide(request: Request):
    require(request, "teacher")
    from src.mvp.pack import load_problem
    pack, rubric = load_problem()
    return render(request, "mvp_teacher_guide.html", pack=pack, rubric=rubric, cards=stage_cards())
