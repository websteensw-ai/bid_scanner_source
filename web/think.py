"""사고 성장 학습 화면 — 초기 사고역량 진단·적응형 추천 (학생), 지식자산 DB·AI 1차 구조화 (교사).

지식자산 기본계획 ⅩⅤ장. 학생은 무엇을 생각할지 선택하고, 시스템은 어느 깊이에서 생각하게 할지를 설계한다 (16절).
학생 화면에는 원천 자료의 전문을 싣지 않는다 (공개 범위는 Source.public).
"""
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

import web.main as _main
from src.mvp import ai as roles_mod
from src.think.adaptive import Adaptive, LLMDiagnoser, ThinkState, demo_diagnose, structure_draft
from src.think.kb import ASSET_TYPES, COPYRIGHT, MODES, PUBLIC, TOPIC_FORMS, catalog, inventory, knowledge
from web.main import env, redirect, render, require

router = APIRouter()
env.filters["comp"] = lambda ids: [knowledge().competencies.name(i) for i in ids]
PATH_KO = {"recommended": "맞춤 추천학습", "interest": "관심주제 선택학습", "explore": "지적 탐험학습"}
REBUTTAL_KO = {"low": "낮음", "mid": "중간", "high": "높음"}
env.globals.update(PATH_KO=PATH_KO, MODES=MODES, TOPIC_FORMS=TOPIC_FORMS, REBUTTAL_KO=REBUTTAL_KO,
                   ASSET_TYPES=ASSET_TYPES, PUBLIC_KO=PUBLIC, COPYRIGHT_KO=COPYRIGHT)


def _load(user: dict, sid: str | None = None):
    state = _main.get_store().load(sid or user["id"])
    return state, Adaptive(ThinkState.model_validate(state.think or {}))


def _save(state, ad: Adaptive, user: dict) -> None:
    state.think = ad.ts.model_dump(mode="json")
    _main.get_store().save(state, is_demo=state.student_id.startswith("demo-"), name=user.get("name", ""))


def _provider(user: dict):
    return roles_mod.get_roles(demo=bool(user.get("is_demo"))).get("provider")


# ---------------------------------------------------------------- 학생
@router.get("/think", response_class=HTMLResponse)
def think_home(request: Request, path: str = "recommended", interest: str = ""):
    user = require(request, "student")
    _, ad = _load(user)
    if not ad.ts.diagnosed:
        return redirect("/think/diagnose")
    path = path if path in PATH_KO else "recommended"
    kb = ad.kb
    return render(request, "think_home.html", ad=ad, kb=kb, tab=path, interest=interest,
                  need=ad.most_needed(), recs=ad.recommend(path, interest or None),
                  interests=kb.diagnostic["interests"], current=ad.current())


@router.get("/think/diagnose", response_class=HTMLResponse)
def think_diagnose(request: Request):
    user = require(request, "student")
    _, ad = _load(user)
    return render(request, "think_diagnose.html", tasks=ad.kb.diagnostic["tasks"], ad=ad,
                  interests=ad.kb.diagnostic["interests"], error=None)


@router.post("/think/diagnose", response_class=HTMLResponse)
async def think_diagnose_post(request: Request):
    user = require(request, "student")
    state, ad = _load(user)
    form = await request.form()
    tasks = ad.kb.diagnostic["tasks"]
    answers = {t["id"]: str(form.get(t["id"], "")).strip() for t in tasks}
    choice = str(form.get("choice", ""))
    if sum(1 for v in answers.values() if len(v) >= 10) < 2:
        return render(request, "think_diagnose.html", tasks=tasks, ad=ad, interests=ad.kb.diagnostic["interests"],
                      error="적어도 두 과제는 한두 문장 이상 써 주세요. 정답을 찾는 시험이 아니에요.", answers=answers)
    p = _provider(user)
    try:
        d = LLMDiagnoser(p)(ad.kb, answers, choice) if p else demo_diagnose(ad.kb, answers, choice)
    except Exception:          # 진단이 실패해도 학생 글은 잃지 않는다
        d = demo_diagnose(ad.kb, answers, choice)
    ad.apply_diagnosis(d)
    ad.ts.interests = [x for x in form.getlist("interests") if x in ad.kb.diagnostic["interests"]][:3]
    _save(state, ad, user)
    return redirect("/think/profile")


@router.get("/think/profile", response_class=HTMLResponse)
def think_profile(request: Request):
    user = require(request, "student")
    _, ad = _load(user)
    if not ad.ts.diagnosed:
        return redirect("/think/diagnose")
    return render(request, "think_profile.html", ad=ad, kb=ad.kb, d=ad.ts.diagnoses[-1], need=ad.most_needed())


@router.post("/think/interests")
async def think_interests(request: Request):
    user = require(request, "student")
    state, ad = _load(user)
    form = await request.form()
    ad.ts.interests = [x for x in form.getlist("interests") if x in ad.kb.diagnostic["interests"]][:3]
    _save(state, ad, user)
    return redirect("/think")


@router.post("/think/start/{topic_id}")
async def think_start(request: Request, topic_id: str):
    user = require(request, "student")
    state, ad = _load(user)
    form = await request.form()
    path = str(form.get("path", "recommended"))
    if not any(h.topic == topic_id and h.finished_at is None for h in ad.ts.history):
        try:
            ad.start(topic_id, path if path in PATH_KO else "recommended")
        except ValueError:
            return redirect("/think")
        _save(state, ad, user)
    return redirect(f"/think/topic/{topic_id}")


@router.get("/think/topic/{topic_id}", response_class=HTMLResponse)
def think_topic(request: Request, topic_id: str):
    user = require(request, "student")
    _, ad = _load(user)
    t = ad.kb.topic(topic_id)
    h = next((h for h in reversed(ad.ts.history) if h.topic == topic_id), None)
    if t is None or h is None:
        return redirect("/think")
    return render(request, "think_topic.html", t=t, h=h, kb=ad.kb, ad=ad,
                  arcs=[ad.kb.archetype(a) for a in t.archetypes])


@router.post("/think/topic/{topic_id}/first")
async def think_first(request: Request, topic_id: str):
    user = require(request, "student")
    state, ad = _load(user)
    form = await request.form()
    try:
        ad.save_first_thought(topic_id, str(form.get("text", "")))
    except ValueError:
        return redirect("/think")
    _save(state, ad, user)
    return redirect(f"/think/topic/{topic_id}")


# ---------------------------------------------------------------- 교사
@router.get("/teacher/knowledge", response_class=HTMLResponse)
def kb_home(request: Request, src: str = ""):
    require(request, "teacher")
    kb = knowledge()
    sel = next((s for s in kb.sources if s.id == src), None)
    return render(request, "knowledge.html", kb=kb, st=kb.stats(), pilot=kb.pilot_progress(), sel=sel,
                  smap=kb.source_map(sel.id) if sel else [], cross=kb.cross_candidates(), draft=None, books=catalog(), inv=inventory())


@router.post("/teacher/knowledge/structure", response_class=HTMLResponse)
async def kb_structure(request: Request):
    user = require(request, "teacher")
    form = await request.form()
    kb = knowledge()
    title, text = str(form.get("title", "")).strip(), str(form.get("text", "")).strip()
    draft = None
    if title and len(text) >= 50:
        try:
            draft = structure_draft(kb, title, text, _provider(user))
        except Exception as e:  # noqa: BLE001 — 초안 도구는 실패를 화면에 알린다
            draft = {"title": title, "_error": f"구조화에 실패했어요: {type(e).__name__}"}
    return render(request, "knowledge.html", kb=kb, st=kb.stats(), pilot=kb.pilot_progress(), sel=None, smap=[],
                  cross=kb.cross_candidates(), draft=draft, books=catalog(), inv=inventory(), draft_yaml=yaml.safe_dump(draft, allow_unicode=True, sort_keys=False) if draft else "",
                  title=title, text=text, short=bool(title or text) and not draft)


@router.get("/teacher/knowledge/template.yaml")
def kb_template(request: Request):
    require(request, "teacher")
    body = (_main.ROOT / "content" / "knowledge" / "README.md").read_text(encoding="utf-8")
    return Response(body, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=knowledge_template.md"})
