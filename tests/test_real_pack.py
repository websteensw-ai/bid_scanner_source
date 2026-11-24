"""실제 출제 문제 1 (BASIC-Q1) — 제시문 (가)~(라) 원문으로 엔진 전 과정이 도는지."""
from src.learning.state import LearnerState
from src.mvp import ai
from src.mvp.engine import MvpEngine
from src.mvp.pack import load_problem
from src.mvp.text import official_count

REAL = (
    "(가)의 관점에서 이순신은 공적 의무를 성실히 수행한 인물이다. 그는 상관이 진영의 오동나무를 베어 가려 하자 공물을 사사로이 처분할 수 없다며 거절했고, 친구가 편지를 빼 주겠다는 제의도 물리쳤다. "
    "이런 행적은 아테네의 배심원이 레이투르기아를 보고 소송 당사자를 판단했듯이 그의 품성과 신뢰성을 판단하는 정황 증거가 된다. 그러므로 공동체에 기여한 사람의 말은 언제나 옳다.\n"
    "(나)의 관점에서 이순신은 사심을 버린 내면의 수양이 나라를 위한 행동으로 이어진 인물이다. 그는 모함을 당할 수 있는 처지에서도 스스로 부끄러움이 없었기에 선공후사를 실천했고, 전공보다 적을 무찌르는 나라의 일을 앞세웠다. "
    "이는 자신을 연마해 공동체를 위한 의무 실행의 동력으로 삼은 정돈된 인격자의 모습이다.\n"
    "두 설명은 인물을 판단하는 근거를 어디에서 찾는가에서 초점이 다르다. (가)는 밖으로 드러난 공적 행적과 그것이 주는 신뢰에 주목하고, (나)는 그 행동을 낳은 안의 수양에 주목한다. "
    "그러나 (나)도 수양이 공동체를 위한 행동의 동력이 된다고 보므로, 두 관점은 서로를 부정하지 않고 같은 인물의 다른 층위를 비춘다."
)
FIXED = REAL.replace("그러므로 공동체에 기여한 사람의 말은 언제나 옳다.",
                     "다만 이런 정황은 법률적 증거 못지않은 판단의 잣대일 뿐이다.")


def test_real_pack_loads_with_original_passages():
    pack, rubric = load_problem("BASIC-Q1")
    text = " ".join(p.text for ps in pack.exam.passages for p in ps.paragraphs)
    assert "이순신" in text and "레이투르기아" in text and "마르쿠스 아우렐리우스" in text and "캉유웨이" in text
    assert [p.id for p in pack.exam.passages] == ["가", "나", "다", "라"]
    assert pack.designated_passages == ["가", "나", "다"]
    assert "박정우" not in text and pack.model_answers == []
    assert rubric.full_id == "BASIC-Q1-RUBRIC-v1.0"


def test_real_pack_full_flow():
    assert official_count(REAL) <= 700
    e = MvpEngine(LearnerState(student_id="r"), ai.get_roles(demo=True))
    a = e.start("BASIC-Q1")
    assert a.pack_id == "BASIC-Q1"
    for sid in ["0", "1", "2", "3", "4", "5"]:
        while e.run().status == "in_progress":
            e.skip_subgoal()
        e.submit_summary({o.key: "(다)를 각각 (가)와 (나) 관점 가-3 공적 의무 신뢰 판단 나-1 수양 동력 다-1 공물 다-2 선공후사 비교 초점 근거 700 문단 빼고"
                          for o in e.cards.get(sid).outputs})
    e.autosave(REAL)
    d = e.complete_draft()
    e.submit_selfcheck([{"key": c.key, "judgment": "keep", "quote": d.body[:10], "reason": "확인"}
                        for c in e.cards.get("6").selfcheck], "a", "b")
    e.save_pre_revision(d.body)
    sub = e.submit()
    ev = e.attempt.latest_eval(sub.id)
    e.submit_diagnosis("a", "b", {})
    levels = {r.code: r.level for r in ev.items}
    assert levels["B3"] <= 2 and levels["C2"] >= 3 and levels["D2"] >= 3     # 과잉 단정은 B3 에서 잡힘
    e.to_threads()
    assert any("B3" in x.rubric_refs for x in e.attempt.annotations if x.nature == "correction")
    e.to_revise()
    ev2 = e.submit_revision(FIXED)
    assert ev2.total > ev.total
