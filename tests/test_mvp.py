"""6단계 논술학습 MVP 테스트 — 규칙(코드로 강제할 것)과 웹 전 과정."""
import json
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from src.learning.state import LearnerState
from src.mvp import ai
from src.mvp.engine import MvpEngine, MvpError
from src.mvp.guardrail import FALLBACK, rule_check
from src.mvp.models import EvalItem
from src.mvp.pack import load_problem, stage_cards
from src.mvp.scoring import compute, merge_runs
from src.mvp.text import cells_used, layout, official_count
from web import store as store_mod
from web.main import app

PACK, RUBRIC = load_problem()
MODEL = PACK.model_answers[0].text
BAD = MODEL.replace("다만 (가)에 따르면 이 신뢰는 그를 믿을 근거일 뿐, 그의 제안이 옳다는 보증은 아니다.",
                    "그러므로 그의 주장은 언제나 옳다.")


# ---------------------------------------------------------------- 데이터
def test_pack_and_cards_validate():
    cards = stage_cards()
    assert cards.order() == ["0", "1", "2", "3", "4", "5", "6", "6.1"]
    assert sum(a.points for a in RUBRIC.areas) == 100
    assert len(RUBRIC.items) == 12
    assert {s.support for s in cards.ladder} == {"independent", "question_then_revised", "scaffolded",
                                                 "explained_then_restated"}


def test_tutor_view_hides_model_answer_and_rubric():
    v = PACK.view_tutor("1", "S1-1")
    blob = json.dumps({k: str(x) for k, x in v.items()}, ensure_ascii=False)
    assert "model_answers" not in v and "rubric" not in v
    assert MODEL[:30] not in blob
    assert all("1" in e.stages for e in v["error_patterns"])
    assert set(PACK.view_student()) == {"meta", "exam"}


# ---------------------------------------------------------------- 글자 수·원고지
def test_official_count_rules():
    assert official_count("가나 다.\n라") == 6          # 공백·부호 포함, 줄바꿈 제외
    assert official_count("  들여쓰기") == 6             # 학생이 넣은 앞 공백도 센다
    assert official_count("한̀") == 1               # 결합 문자는 한 글자


def test_layout_rules():
    rows = layout("가" * 19 + ".")
    assert rows[0][0] == "" and rows[0][19] == "가."   # 첫 칸 비움, 줄 끝 부호는 마지막 칸에 함께
    assert len(rows) == 1
    assert layout("ab12")[0][1:3] == ["ab", "12"]      # 소문자·숫자 두 자씩
    assert layout("다.  그러나")[0][1:5] == ["다", ".", "그", "러"]   # 표시용 공백 정리
    assert cells_used("가나다\n라") == 22            # 1행 20칸 + 들여쓰기·라


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_js_layout_matches_python(tmp_path):
    from pathlib import Path
    js = Path("public/manuscript.js").read_text(encoding="utf-8")
    samples = ["가" * 19 + ".", "ab12 가나", "다.  그러나 그는,  말했다.\n둘째 문단" + "나" * 30, BAD]
    script = ("var window={addEventListener(){}};var document={getElementById(){return null}};" + js +
              f";console.log(JSON.stringify({json.dumps(samples, ensure_ascii=False)}.map(window.mvpLayout)))")
    f = tmp_path / "t.js"
    f.write_text(script, encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert out == [layout(s) for s in samples]


# ---------------------------------------------------------------- 채점 계산
def test_scoring_is_code_computed():
    items = [EvalItem(code=i.code, level=4) for i in RUBRIC.items]
    items[0].level = 2                                  # A1 12점 × 2/4 = 6
    r = compute(RUBRIC, items, 600, 700)
    assert r["area_scores"]["A"] == 14 and r["total"] == 94 and not r["provisional"]
    r = compute(RUBRIC, [EvalItem(code=i.code, level=4) for i in RUBRIC.items], 750, 700)
    assert r["over_chars"] == 50 and r["area_scores"]["E"] == 5   # E2 = 0
    items = [EvalItem(code=i.code, level=4) for i in RUBRIC.items]
    items[3].level = None
    assert compute(RUBRIC, items, 600, 700)["provisional"]      # 보류는 0점과 구분


def test_double_grading_mismatch():
    a = [EvalItem(code="B3", level=1)]
    b = [EvalItem(code="B3", level=3)]
    merged, mismatch = merge_runs([a, b])
    assert mismatch == ["B3"] and merged[0].review_recommended


# ---------------------------------------------------------------- 응답 검사기
def test_guardrail_rules():
    assert not rule_check("왜 그런가요? 근거는요?", [])["ok"]
    assert not rule_check("가" * 300, [])["ok"]
    assert not rule_check(MODEL.split(".")[0] + ".", [MODEL])["ok"]
    assert rule_check("원문의 어느 대목에서 그렇게 읽었나요?", [MODEL])["ok"]


class LeakyTutor(ai.Tutor):
    def respond(self, ctx, feedback=""):
        return "정답은 이거예요? 그리고 저거예요?", ai.TutorJudgment(subgoal_id=ctx.subgoal.id)


def test_guardrail_regenerates_then_falls_back():
    e = MvpEngine(LearnerState(student_id="x"), {"tutor": LeakyTutor(), "judge": ai.DemoJudge(),
                                                 "grader": ai.DemoGrader(), "provider": None})
    e.start()
    t = e.student_turn("논제는 설명하라는 거예요")
    assert t.text == FALLBACK and len(t.rejected_drafts) == 2 and t.check.get("fallback")


# ---------------------------------------------------------------- 엔진 규칙
def engine():
    e = MvpEngine(LearnerState(student_id="s"), ai.get_roles(demo=True))
    e.start()
    return e


GOOD0 = "(다)를 (가)와 (나)의 관점에서 각각 설명하고, 두 설명의 초점 차이를 밝혀야 해요. 제시문에서 관점과 사례를 잇는 대목을 근거로 찾아 확인하고, 700자 이내로 써요."


def to_stage1(e):
    e.student_turn(GOOD0)
    e.student_turn("아직 두 관점의 정확한 내용은 모르겠어요.")
    assert e.submit_summary({k: v for k, (v, _) in e.summary_candidates().items()}).verdict == "pass"
    assert e.attempt.current == "1"


def test_ladder_one_rung_per_turn_and_answer_requests():
    e = engine()
    to_stage1(e)                                       # 보충 경로가 따로 없는 단계: 두 번째 정답 요구는 5칸까지
    e.student_turn("정답 알려줘")
    assert e.run().rung == 1
    e.student_turn("그냥 답 알려주세요")
    assert e.run().rung == 5
    assert e.run().support == "explained_then_restated"


def test_stage0_support_path_climbs_one_rung_at_a_time():
    """0단계 설계 Ⅶ: 질문 → 논제를 짧게 나눔 → 빈 틀 → 설명(지원 후 이해). 한 칸씩."""
    e = engine()
    texts = [e.student_turn(t).text for t in ["정답 알려줘", "그냥 답 알려주세요", "모르겠어요", "모르겠어요"]]
    assert e.run().rung == 4 and e.run().support == "explained_then_restated"
    assert "짧게 나눠" in texts[1] and "빈칸" in texts[2] and "도움말" in texts[3]
    assert "정답보다 먼저" in texts[0]


def test_off_task_redirect_keeps_rung_and_danger_flags():
    e = engine()
    t = e.student_turn("배고파")
    assert e.run().rung == 0 and "논제" in t.text
    t = e.student_turn("요즘 너무 힘들어서 죽고 싶어요")
    assert e.run().status == "flagged" and "1388" in t.text
    assert any(a.kind == "danger" for a in e.attempt.alerts)
    with pytest.raises(MvpError):
        e.student_turn("계속할래요")


def test_stage_turn_limit_flags():
    e = engine()
    e.cards = e.cards.model_copy(update={"limits": {**e.cards.limits, "turns_per_stage": 3}})
    for _ in range(4):
        e.student_turn("음 글쎄요 잘")
    assert e.run().status == "flagged" and any(a.kind == "stall" for a in e.attempt.alerts)


def test_summary_candidates_only_from_student_and_provenance():
    e = engine()
    e.student_turn(GOOD0)
    e.student_turn("아직 두 관점의 정확한 내용은 모르겠어요.")
    tutor_texts = {t.text for t in e.run().turns if t.role == "tutor"}
    cands = e.summary_candidates()
    assert all(v not in tutor_texts for v, _ in cands.values())
    fields = {k: v for k, (v, _) in cands.items()}
    fields["unsure"] = "(가)와 (나)의 실제 관점"
    out = e.submit_summary(fields)
    assert out.verdict == "pass" and out.fields["memo"].source == "student_turn"
    assert out.fields["unsure"].source == "typed"
    assert e.attempt.current == "1" and e.attempt.stages["0"].status == "completed"


# ---------------------------------------------------------------- 0단계 설계 (2026-11-14)
def test_stage0_first_screen_and_opener():
    e = engine()
    r = e.run()
    assert r.turns[0].role == "tutor" and "실제 출제 문제" in r.turns[0].text and "자신의 말로 설명" in r.turns[0].text
    assert e.pack.exam.points == 100 and e.pack.exam.minutes == 100
    assert [p.id for p in e.pack.exam.passages] == ["가", "나", "다", "라"]
    assert e.pack.designated_passages == ["가", "나", "다"]


def test_stage0_main_simulation_scenes():
    """주 시뮬레이션 장면 1~8 의 흐름: 주제·평가 오해 → 지시 표현 확인, 여러 항목 동시 확인, 막연한 다짐 거절, (라) 질문."""
    e = engine()
    t = e.student_turn("공동체를 위해 행동하는 것이 왜 중요한지 쓰는 문제 같아요. 박정우가 훌륭한 인물이라는 걸 설명하면 될 것 같아요.")
    assert t.judgment.error_code == "topic_or_opinion" and "요구하는 표현" in t.text
    e.student_turn("그대로 요구한 표현은 없어요. (다)를 (가)와 (나)의 관점에서 각각 설명하라고 되어 있어요.")
    sg = e.run().subgoals
    assert sg["S0-1"].status == "met" and sg["S0-2"].status == "met"          # 한 응답에서 두 항목
    t = e.student_turn("이해했어요")
    assert t.judgment.intent == "vague" and sg["S0-3"].status != "met"
    t = e.student_turn("그런데 (라)도 있으니 최종 답안에 꼭 넣어야 하나요?")
    assert t.judgment.intent == "undesignated" and "지정한 제시문" in t.text and "(라)" not in t.text
    for x in ["아니요. 두 설명의 초점 차이도 밝혀야 해요.", "그 설명을 뒷받침하는 대목을 원문에서 찾아 확인할게요.",
              "700자 이내이고 제목은 안 써요."]:
        e.student_turn(x)
    assert e.run().status == "summarizing"                                     # 핵심 4기준 충족
    t = e.student_turn("두 관점의 정확한 내용은 아직 확인하지 못했어요.")          # 선택 항목(불확실성)
    assert e.run().subgoals["S0-6"].status == "met" and "풀이 준비 메모" in t.text
    out = e.submit_summary({k: v for k, (v, _) in e.summary_candidates().items()})
    assert out.verdict == "pass"
    r0 = e.attempt.stages["0"]
    assert r0.verdict == "ready" and r0.turns[-1].text.startswith("무엇을 해야 하는지")
    lr = e.link_record("0")
    assert lr["first"].startswith("공동체를 위해") and lr["issues"] and "700자" in lr["memo"]
    assert e.attempt.thinking                                                  # 최초 이해 → 수정
    r1 = e.run()                                                               # 1단계는 준비 메모에서 시작
    assert r1.stage == "1" and "내 준비 메모" in r1.turns[0].text and "무엇을 해야" not in r1.turns[0].text


def test_stage0_proficient_student_moves_on_quickly():
    e = engine()
    e.student_turn(GOOD0)
    assert e.run().status == "summarizing" and e.run().student_turns() == 1


def test_stage0_memo_must_show_core_criteria():
    e = engine()
    e.student_turn(GOOD0)
    out = e.submit_summary({"memo": "공동체가 중요하다는 내 생각을 자유롭게 쓰는 문제다. 열심히 잘 쓰겠다.", "unsure": "없음 없음"})
    assert out.verdict == "fail" and e.attempt.stages["0"].verdict == "unconfirmed"


def test_stage0_with_support_is_recorded():
    e = engine()
    for t in ["모르겠어요", "모르겠어요"]:
        e.student_turn(t)
    e.student_turn(GOOD0)
    e.student_turn("아직 모르는 부분은 (가)의 관점이에요.")
    e.submit_summary({k: v for k, (v, _) in e.summary_candidates().items()})
    assert e.attempt.stages["0"].verdict == "ready_with_support"


def advance_to_writing(e):
    for sid in ["0", "1", "2", "3", "4", "5"]:
        while e.run().status == "in_progress":
            e.skip_subgoal()
        f = {o.key: "(다)를 각각 가-2 공동체 기여 행적 신뢰 나-1 수양 내면 다-1 곡식 다-2 일기 비교 초점 근거 실패 이어 문단 빼고 700 관점 사례 설명"
             for o in e.cards.get(sid).outputs}
        assert e.submit_summary(f).verdict == "pass"
    assert e.attempt.current == "6"


def test_writing_versions_selfcheck_and_review_flow():
    e = engine()
    advance_to_writing(e)
    with pytest.raises(MvpError):
        e.autosave("가" * 900)                          # 800칸 초과 입력은 막음
    e.autosave(BAD, [40])
    assert any(a.kind == "paste" for a in e.attempt.alerts)
    assert "제출 후" in e.help_request("(가) 관점이 맞나요?")
    assert "글자 수" in e.help_request("글자 수는 어떻게 세요?")
    ind = e.complete_draft()
    with pytest.raises(MvpError):
        e.complete_draft()                              # 독립 초고는 고정
    keys = [c.key for c in e.cards.get("6").selfcheck]
    with pytest.raises(MvpError):                       # '유지'인데 구절 없음 → 제출 불가
        e.submit_selfcheck([{"key": k, "judgment": "keep", "reason": "괜찮음"} for k in keys], "a", "b")
    ents = [{"key": k, "judgment": "keep", "quote": ind.body[:15], "reason": "확인함"} for k in keys]
    ents[2] = {"key": "scope", "judgment": "problem", "reason": "언제나 옳다는 지나침"}
    e.submit_selfcheck(ents, "(나) 설명", "(가) 범위")
    pre = e.save_pre_revision(ind.body)
    assert pre.same_as == ind.id
    sub = e.submit()
    a = e.attempt
    assert sub.frozen and a.current == "6.1" and a.review_phase == "diagnose"
    ev = a.latest_eval(sub.id)
    b3 = next(i for i in ev.items if i.code == "B3")
    assert b3.level <= 1 and b3.evidence[0]["quote"] == "그러므로 그의 주장은 언제나 옳다."
    assert sub.body[b3.evidence[0]["start"]:b3.evidence[0]["end"]] == b3.evidence[0]["quote"]
    first = a.annotations[0]
    assert first.rubric_refs == ["B3"] and first.shown
    assert not e.model_answer_open()
    e.submit_diagnosis("x", "y", {"p1": "(가) 관점 설명"})
    e.to_threads()
    n = first.number
    e.thread_reply(n, "모르겠어요")
    e.thread_reply(n, "모르겠어요")
    assert "설명 지원" in first.support_steps
    with pytest.raises(MvpError):
        e.decide(n, "reject", "")
    e.decide(n, "accept", "신뢰와 참은 달라요", "그의 제안이 옳다는 보증은 아니다")
    e.to_revise()
    assert a.temp_draft == sub.body                     # 결정 4: 제출본 본문을 미리 채움
    fin_body = sub.body.replace("그러므로 그의 주장은 언제나 옳다.", "하지만 그 신뢰가 그의 제안이 옳다는 보증은 아니다.")
    ev2 = e.submit_final(fin_body)
    assert ev2.total > ev.total
    assert first.status == "resolved" and first.revision_link["method"] == "proposal"
    assert a.selfcheck_result["scope"] == "found_unresolved"
    assert e.model_answer_open()
    e.finish_review("신뢰와 참을 구별했나?")
    ref = e.save_reflection({"A1": "3 (가)로 설명", "A5": ["묻고 답하기"]}, submit=True)
    assert "A5" not in ref.answers and a.status == "done"   # 의견 문항은 학습 DB 에 넣지 않음


def test_reject_with_valid_reason_withdraws():
    e = engine()
    advance_to_writing(e)
    e.autosave(BAD)
    d = e.complete_draft()
    e.submit_selfcheck([{"key": c.key, "judgment": "keep", "quote": d.body[:10], "reason": "확인"}
                        for c in e.cards.get("6").selfcheck], "a", "b")
    e.save_pre_revision(d.body)
    e.submit()
    e.submit_diagnosis("", "", {})
    e.to_threads()
    n = e.attempt.annotations[0].number
    assert e.decide(n, "reject", "짧음").status == "active"
    assert e.decide(n, "reject", "가-3 문단을 근거로 의도한 표현입니다").status == "withdrawn"


# ---------------------------------------------------------------- 웹 전 과정
@pytest.fixture()
def client(monkeypatch):
    mem = store_mod.MemoryStore()
    monkeypatch.setattr("web.main.get_store", lambda: mem)
    c = TestClient(app)
    c.mem = mem
    c.post("/login", data={"login_id": "test", "password": "testpoc"})
    return c


def test_web_full_flow(client):
    c = client
    assert "학습 시작하기" in c.get("/mvp").text
    r = c.post("/mvp/start", follow_redirects=True)
    assert "처음 한 번은 끝까지" in r.text
    c.post("/mvp/guide/done")
    r = c.get("/mvp/stage/0")
    assert "가-1" in r.text and PACK.exam.prompt in r.text
    assert MODEL[:25] not in r.text and PACK.explanation_criteria["ga"] not in r.text
    assert "총 100점" in r.text and "문제 앞에서 스스로 물어볼 질문" in r.text and "문제 접근 요령" in r.text
    assert "실제 출제 문제" in r.text                                   # 튜터의 최초 안내
    r = c.post("/mvp/stage/0/say", data={"text": GOOD0}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and 'id="dialogue"' in r.text and "subgoal_status" not in r.text
    c.post("/mvp/stage/0/say", data={"text": "아직 두 관점의 정확한 내용은 모르겠어요."})
    r = c.get("/mvp/stage/0")
    assert "풀이 준비 메모" in r.text
    r = c.post("/mvp/stage/0/summary", data={"f_memo": GOOD0, "f_unsure": "두 관점의 정확한 내용"},
               follow_redirects=True)
    assert "1단계" in r.text
    # 나머지 단계는 엔진으로 빠르게 진행 후 저장
    sid = next(iter(c.mem.states))
    e = MvpEngine(c.mem.load(sid), ai.get_roles(demo=True))
    for s in ["1", "2", "3", "4", "5"]:
        while e.run().status == "in_progress":
            e.skip_subgoal()
        e.submit_summary({o.key: "가-2 공동체 기여 행적 신뢰 나-1 수양 내면 다-1 곡식 다-2 일기 비교 초점 근거 실패 이어 문단 빼고"
                          for o in e.cards.get(s).outputs})
    e.save()
    c.mem.save(e.state, is_demo=True, name="")
    r = c.get("/mvp/stage/6")
    assert "독립 작성" in r.text and 'spellcheck="false"' in r.text and "nx-chatbox" not in r.text
    r = c.post("/mvp/write/autosave", json={"body": BAD, "pastes": [5]})
    assert r.json()["ok"] and r.json()["chars"] == official_count(BAD)
    c.post("/mvp/write/draft", data={"body": BAD})
    form = {"confident": "a", "uncertain": "b"}
    for k in ["tasks", "evidence", "scope", "form", "length"]:
        form |= {f"j_{k}": "keep", f"q_{k}": BAD[:12], f"r_{k}": "확인"}
    c.post("/mvp/write/selfcheck", data=form)
    c.post("/mvp/write/pre_revision", data={"body": BAD})
    r = c.post("/mvp/write/submit", follow_redirects=True)
    assert "짧은 자기진단" in r.text and "판단 이유" not in r.text      # 결과는 자기진단 후 공개
    r = c.post("/mvp/review/diagnose", data={"confident": "a", "uncertain": "b", "p1": "(가) 관점 설명"},
               follow_redirects=True)
    assert "항목별 판단 이유" in r.text and "B3" in r.text
    r = c.post("/mvp/review/threads", follow_redirects=True)
    assert "ann-num" in r.text and "①" in r.text
    c.post("/mvp/review/decide", data={"number": "1", "decision": "accept", "reason": "맞아요"})
    c.post("/mvp/review/revise")
    r = c.post("/mvp/review/final", data={"body": BAD.replace("그러므로 그의 주장은 언제나 옳다.", "하지만 신뢰가 참을 보증하지는 않는다.")},
               follow_redirects=True)
    assert "첨삭 후 최종본" in r.text and "예시답안" in r.text
    r = c.post("/mvp/review/finish", data={"next_question": "신뢰와 참 구별?"}, follow_redirects=True)
    assert "돌아보기" in r.text
    r = c.post("/mvp/reflect", data={"A1": "3 (가)로 설명", "A6": "많이 도움이 됐어요", "fb_send": "1", "act": "submit"},
               follow_redirects=True)
    assert "저장했어요" in r.text
    fb = c.mem.list_feedback()
    assert fb and fb[0]["user_id"] is None and "A1" not in fb[0]["answers"]      # 익명·분리 저장
    dl = c.get("/mvp/records/download")
    assert dl.status_code == 200 and "scaffold_level" not in dl.text and "support_level" not in dl.text
    # 교사 화면 (데모 관리자는 자기 기록만)
    r = c.get("/teacher/mvp")
    assert "검토 대기열" in r.text and "학생별 진행" in r.text
    r = c.get(f"/teacher/mvp/student/{sid}?tab=eval")
    assert "첨삭 후" in r.text and "수정" in r.text
    r = c.get(f"/teacher/mvp/student/{sid}?tab=timeline")
    assert "사다리" in r.text or "건너뛰" in r.text
    assert c.get("/teacher/mvp/student/someone-else").status_code == 403
    assert c.get("/teacher/mvp/feedback").status_code == 200
    assert "예시 장면" in c.get("/teacher/mvp/guide").text


def test_teacher_regrade_keeps_history(client):
    e = engine()
    advance_to_writing(e)
    e.autosave(BAD)
    d = e.complete_draft()
    e.submit_selfcheck([{"key": c.key, "judgment": "keep", "quote": d.body[:10], "reason": "확인"}
                        for c in e.cards.get("6").selfcheck], "a", "b")
    e.save_pre_revision(d.body)
    e.submit()
    prev = e.attempt.evaluations[-1]
    with pytest.raises(MvpError):
        e.teacher_regrade(prev.id, "B3", 3, "", "교사")
    ev = e.teacher_regrade(prev.id, "B3", 3, "표현은 강하나 범위 인식 있음", "교사")
    assert ev.replaces == prev.id and ev.evaluator == "teacher:교사" and ev.total > prev.total
    assert prev in e.attempt.evaluations and re.search("이전 수준", next(i for i in ev.items if i.code == "B3").reason)


def test_old_attempt_with_previous_stage0_still_opens():
    st = LearnerState(student_id="old")
    e = MvpEngine(st, ai.get_roles(demo=True))
    e.start()
    raw = e.attempt.model_dump(mode="json")
    raw["stages"]["0"]["subgoals"] = {"S0-1": {"status": "met"}, "S0-2": {"status": "not_yet"}, "S0-3": {"status": "not_yet"}}
    st.mvp[e.attempt.id] = raw
    e2 = MvpEngine(st, ai.get_roles(demo=True))
    assert set(e2.run().subgoals) >= {"S0-4", "S0-5", "S0-6"}
    e2.student_turn(GOOD0)
    assert e2.run().status == "summarizing"
