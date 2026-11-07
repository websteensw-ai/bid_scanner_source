"""공통 실행 틀 정책 테스트. 분석 결과를 직접 지정하는 ScriptedAnalyzer 로 정책만 검증한다."""
import pytest

from src.learning.analyzer import Analyzer, DemoAnalyzer, Diagnosis
from src.learning.content import count_chars, load_pack
from src.learning.engine import Engine, LearningError, answered
from src.learning.levels import Level, SupportType
from src.learning.state import LearnerState


class ScriptedAnalyzer(Analyzer):
    name = "scripted"

    def __init__(self, script):
        self.script = list(script)

    def analyze(self, step, answer, evidence, choice, excerpts, context):
        d = self.script.pop(0)
        return d(step) if callable(d) else d


def all_met(step):
    return Diagnosis(met=[c.id for c in step.criteria])


def none_met(error=None):
    def f(step):
        return Diagnosis(met=[], primary_error=error or (step.errors[0].id if step.errors else None))
    return f


def make(script):
    state = LearnerState(student_id="t")
    return state, Engine(state, ScriptedAnalyzer(script))


def test_pack_valid():
    pack = load_pack()
    assert [b.id for b in pack.topics()] == ["L1", "L2", "L3", "L4", "L5"]
    # 학생에게 보이는 제시문 라벨은 중립 기호이고, 출처 정보는 내부 필드에만 있다
    for ex in pack.excerpts.values():
        assert ex.source.is_sample
        assert ex.source.title not in "".join(ex.paragraphs)


def test_independent_first_answer_skips_generalization():
    # 최초 답이 일반화 기준까지 충족하면 일반화 단계 생략 (L1-010·Z-008)
    state, eng = make([all_met, all_met])
    s = eng.start("L1")
    eng.submit(s, "공정한 배분은 기여에 따라 보상을 달리하는 것이다", "둘째 문단")
    assert s.steps["l1_general"].status == "skipped"
    assert s.steps["l1_initial"].level == Level.INDEPENDENT
    eng.submit(s, "규칙은 이유를 알 때 지켜진다")
    assert s.status == "done"
    assert state.criteria["C1"].level == Level.INDEPENDENT


def test_direction_limit_then_explanation_then_demo():
    # 같은 판단점 방향 질문 2회 → 설명 → 시범 → 미형성 기록 (Z-018)
    state, eng = make([none_met("e_vague")] * 5)
    s = eng.start("L1")
    for _ in range(5):
        eng.submit(s, "다르게 나눴다")
    ss = s.steps["l1_initial"]
    types = [sp.type for sp in ss.supports]
    assert types == [SupportType.DIRECTION, SupportType.DIRECTION,
                     SupportType.EXPLANATION, SupportType.DEMO]
    assert ss.level == Level.NOT_FORMED and ss.status == "done"
    assert s.step_idx == 1        # 다음 활동으로 이동 (자동 탈락·무한 반복 없음)


def test_support_lowers_level():
    state, eng = make([none_met("e_vague"), all_met])
    s = eng.start("L1")
    eng.submit(s, "다르게 나눴다")
    eng.submit(s, "기여에 따라 보상을 달리해야 공정하다")
    assert s.steps["l1_initial"].level == Level.MINIMAL


def test_vocab_does_not_lower_level():
    state, eng = make([all_met])
    s = eng.start("L1")
    eng.request_help(s, "vocab", "공정")
    eng.submit(s, "기여에 따라 보상을 달리해야 공정하다")
    assert s.steps["l1_initial"].level == Level.INDEPENDENT


def test_no_content_help_before_first_attempt_beyond_guide():
    state, eng = make([])
    s = eng.start("L1")
    opts = eng.help_options(s)
    assert "structure" not in opts and "guide" in opts      # 최초 수행 전에는 안내까지만


def test_independent_check_gives_no_hint():
    state, eng = make([all_met, all_met, none_met()])
    s = eng.start("L1")
    eng.submit(s, "첫째 답입니다")        # initial
    eng.submit(s, "둘째 답입니다")        # general (skip 안 될 수도 있으니 진행)
    if s.status != "done":
        step = eng.current_step(s)
        assert step.independent_check
        assert eng.help_options(s) == ["vocab"]
        eng.submit(s, "셋째 답입니다")
        ss = s.steps[step.id]
        assert not [x for x in ss.supports if x.type == SupportType.DIRECTION]
        assert ss.level is None


def test_uncertain_confirm_once_then_flag():
    unc = Diagnosis(uncertain=True)
    state, eng = make([unc, unc])
    s = eng.start("L1")
    eng.submit(s, "음")
    assert s.steps["l1_initial"].supports[-1].type == SupportType.CONFIRM
    eng.submit(s, "글쎄")
    assert s.steps["l1_initial"].level is None
    assert state.flags and state.flags[-1].kind == "uncertain"


def test_answers_are_preserved():
    state, eng = make([none_met("e_vague"), all_met])
    s = eng.start("L1")
    eng.submit(s, "첫 답")
    eng.submit(s, "고친 답")
    atts = s.steps["l1_initial"].attempts
    assert [a.text for a in atts] == ["첫 답", "고친 답"]
    assert [a.kind for a in atts] == ["first", "revised"]
    assert s.first_outputs["l1_initial"] == "첫 답"


def test_pause_resume_keeps_position():
    state, eng = make([none_met("e_vague")])
    s = eng.start("L1")
    eng.submit(s, "다르게 나눴다")
    eng.pause(s)
    assert s.status == "paused"
    s2 = eng.start("L1")
    assert s2 is s and s2.status == "active" and s2.step_idx == 0


def test_version_pinned():
    state, eng = make([])
    s = eng.start("L1")
    assert s.version == load_pack().version


def test_supplement_once_only():
    state, eng = make([all_met, all_met])
    s = eng.start("S1-가")
    eng.submit(s, "첫째 답입니다")
    eng.submit(s, "둘째 답입니다")
    assert s.status == "done" and "S1-가" in state.supplements_done
    assert eng.start("S1-가").status == "done"        # 다시 시작되지 않음
    state.sessions.pop("S1-가")
    with pytest.raises(LearningError):
        eng.start("S1-가")


def test_supplement_practice_does_not_update_criterion_but_recheck_does():
    state, eng = make([all_met, all_met])
    state.criteria["C1"] = __import__("src.learning.state", fromlist=["CriterionRecord"]) \
        .CriterionRecord(level=1, source="L1")
    s = eng.start("S1-가")
    eng.submit(s, "직접 연습")
    assert state.criteria["C1"].level == 1             # 재학습 후 수행은 갱신하지 않음
    eng.submit(s, "재확인 답")
    assert state.criteria["C1"].level == Level.INDEPENDENT


def test_recheck_one_direction_gives_level2_then_unconfirmed_keeps_prior():
    from src.learning.state import CriterionRecord
    state, eng = make([all_met, none_met(), all_met])
    state.criteria["C1"] = CriterionRecord(level=1, source="L1")
    s = eng.start("S1-가")
    eng.submit(s, "연습")
    eng.submit(s, "재확인 1")          # 방향 질문 1회
    eng.submit(s, "재확인 2")
    assert state.criteria["C1"].level == Level.MINIMAL

    state2, eng2 = make([all_met, none_met(), none_met()])
    state2.criteria["C1"] = CriterionRecord(level=1, source="L1")
    s = eng2.start("S1-가")
    eng2.submit(s, "연습")
    eng2.submit(s, "재확인 1")
    eng2.submit(s, "재확인 2")
    assert state2.criteria["C1"].level == 1            # 미확인 종료 시 기존 판단 유지 (S1-143)
    assert any(f.kind == "not_confirmed" for f in state2.flags)


def test_length_limit_counts_and_keeps_draft():
    assert count_chars("가 나\n다") == 4                  # 공백 포함, 줄바꿈 제외
    state, eng = make([all_met] * 30)
    for t in ("L1", "L2", "L3", "L4"):
        s = eng.start(t)
        while s.status != "done":
            eng.submit(s, "답", choice=(eng.current_step(s).choices or [None])[0])
    s = eng.start("L5")
    eng.submit(s, "개요")
    long = "가" * 450
    eng.submit(s, long)                                 # 초고: 초과해도 저장, 자르지 않음
    assert s.outputs["l5_draft"] == long
    eng.submit(s, long, "그대로")                        # 자기검토
    eng.submit(s, long)                                 # 최종 제출: 분량 안내
    ss = s.steps["l5_final"]
    assert ss.supports[-1].point == "length" and s.outputs["l5_final"] == long


def test_full_course_reaches_entry_judgment():
    state, eng = make([all_met] * 40)
    for t in ("L1", "L2", "L3", "L4", "L5"):
        s = eng.start(t)
        while s.status != "done":
            step = eng.current_step(s)
            eng.submit(s, "답", "근거", choice=(step.choices or [None])[0])
    entry = eng.latest_entry()
    assert entry is not None
    assert entry["decision"] == "진입 가능"
    assert all(entry["levels"][c] == 3 for c in ("C1", "C2", "C3", "C4", "C5"))


def test_l4_counter_not_given_before_attempt():
    # 학생이 반론을 시도하기 전에는 시범(구체 반론 예시)을 주지 않는다 (L4-023·L4-062)
    state, eng = make([all_met])
    s = eng.start("L4")
    eng.submit(s, "입론")
    assert eng.current_step(s).id == "l4_counter"
    assert "dont_know" in eng.help_options(s)
    ss = s.steps["l4_counter"]
    assert not ss.supports


def test_demo_analyzer_smoke():
    state = LearnerState(student_id="d")
    eng = Engine(state, DemoAnalyzer())
    s = eng.start("L1")
    eng.submit(s, "이 글은 장수 이야기다")
    assert s.steps["l1_initial"].supports[-1].type == SupportType.DIRECTION
    eng.submit(s, "공정한 배분은 똑같이가 아니라 기여와 성과에 따라 보상하는 것이다", "둘째 문단")
    assert s.steps["l1_initial"].level == Level.MINIMAL


def test_evidence_comes_from_deciding_step():
    # 기준의 근거 응답은 그 수준을 정한 단계의 답이어야 한다 (S1-008)
    state, eng = make([none_met("e_vague")] * 5 + [all_met, all_met])
    s = eng.start("L1")
    for _ in range(5):
        eng.submit(s, "틀린 첫 답")
    eng.submit(s, "일반화 답")
    eng.submit(s, "독립 확인 답")
    rec = state.criteria["C1"]
    assert rec.level == Level.INDEPENDENT
    assert rec.evidence == "독립 확인 답" and rec.source.endswith("l1_check")
    assert rec.supports == []           # 독립 확인 단계에서는 지원 없음


# ---------- 튜터 문답: 답이 아닌 발화 ----------
def _tutor_last(ss):
    return [m for m in ss.messages if m.role == "tutor"][-1]


def test_off_task_redirects_immediately_without_analyzer_or_praise():
    state, eng = make([])                    # 분석기를 부르면 pop 에서 실패 → 규칙으로 처리됐는지 확인
    s = eng.start("L1")
    eng.submit(s, "ㅋㅋㅋㅋ")
    ss = s.steps["l1_initial"]
    msg = _tutor_last(ss)
    assert msg.kind == "redirect" and "중심 생각 한 문장" in msg.text
    assert "잘 잡았어요" not in msg.text                         # 엉뚱한 칭찬 금지
    assert ss.directions == {} and not answered(ss)              # 방향 질문·최초 답으로 세지 않음
    assert "l1_initial" not in s.first_outputs


def test_off_task_does_not_lower_level():
    state, eng = make([all_met])
    s = eng.start("L1")
    eng.submit(s, "배고파요 점심 언제예요")
    eng.submit(s, "공정한 배분은 기여에 따라 보상하는 것이다")
    assert s.steps["l1_initial"].level == Level.INDEPENDENT


def test_repeated_off_task_suggests_break_and_flags_teacher():
    state, eng = make([])
    s = eng.start("L1")
    for t in ("ㅋㅋㅋ", "게임하고 싶어", "asdf"):
        eng.submit(s, t)
    ss = s.steps["l1_initial"]
    assert ss.redirects == 3
    assert "저장하고 나가기" in _tutor_last(ss).text
    assert [f.kind for f in state.flags] == ["attention"]


def test_answer_request_is_refused_without_answer():
    state, eng = make([])
    s = eng.start("L1")
    eng.submit(s, "그냥 정답 좀 알려 주세요")
    msg = _tutor_last(s.steps["l1_initial"])
    assert msg.kind == "redirect" and "정답을 먼저 알려 주지는 않아요" in msg.text
    for crit_word in ("기여", "성과", "보상"):                    # 내용 힌트 없음
        assert crit_word not in msg.text


def test_vocab_question_gets_meaning_and_task_question_gets_guide():
    state, eng = make([])
    s = eng.start("L1")
    eng.submit(s, "공정이 무슨 뜻이에요?")
    ss = s.steps["l1_initial"]
    assert ss.supports[-1].type == SupportType.VOCAB and "치우치지" in ss.supports[-1].text
    eng.submit(s, "이거 뭘 하라는 거예요?")
    assert ss.supports[-1].type == SupportType.GUIDE


def test_question_in_independent_check_gives_no_hint():
    state, eng = make([all_met, all_met])
    s = eng.start("L1")
    eng.submit(s, "첫째 답입니다")
    if eng.current_step(s).id != "l1_check":
        eng.submit(s, "둘째 답입니다")
    eng.submit(s, "어떻게 해야 해요?")
    ss = s.steps["l1_check"]
    assert ss.supports[-1].type == SupportType.REDIRECT
    assert "힌트는 드릴 수 없어요" in ss.supports[-1].text


def test_demo_analyzer_flags_unrelated_answer_as_off_task():
    state = LearnerState(student_id="d")
    eng = Engine(state, DemoAnalyzer())
    s = eng.start("L1")
    eng.submit(s, "아이돌 콘서트 가고 싶다")
    assert _tutor_last(s.steps["l1_initial"]).kind == "redirect"
