import pytest

from src.learning.entry import EntryDecision, judge_entry
from src.learning.levels import Criterion as C
from src.learning.levels import Level, SupportType, level_after


def lv(a, b, c, d, e):
    return dict(zip(list(C), [a, b, c, d, e], strict=True))


@pytest.mark.parametrize("levels, expected", [
    # S2-061: 기준 ②가 3, 2, 1일 때 전체 판정이 달라지는지
    (lv(3, 3, 3, 2, 2), EntryDecision.READY),
    (lv(3, 2, 3, 2, 2), EntryDecision.CONDITIONAL),
    (lv(3, 1, 3, 2, 2), EntryDecision.SUPPLEMENT),
    # 모두 3
    (lv(3, 3, 3, 3, 3), EntryDecision.READY),
    # ①·②가 3이 아니면 3이 셋 이상이어도 진입 가능 아님
    (lv(2, 3, 3, 3, 3), EntryDecision.CONDITIONAL),
    # ③~⑤ 중 하나만 1 → 조건부 (S2-058)
    (lv(3, 3, 1, 3, 3), EntryDecision.CONDITIONAL),
    # ③~⑤ 중 둘 이상 1 → 보충 (S2-059)
    (lv(3, 3, 1, 1, 3), EntryDecision.SUPPLEMENT),
    # 어느 기준이든 0 → 보충
    (lv(3, 3, 3, 3, 0), EntryDecision.SUPPLEMENT),
    # ① 1 → 보충
    (lv(1, 3, 3, 3, 3), EntryDecision.SUPPLEMENT),
    # 미확인 → 보류 (Z-028)
    (lv(3, 3, None, 3, 3), EntryDecision.HOLD),
    # S4-027 예: ③3·④2 (다른 조건 충족) → 진입 가능
    (lv(3, 3, 3, 2, 2), EntryDecision.READY),
    # S5-026 예: ⑤2 → 조건부, ⑤1 → 조건부, ⑤0 → 보충
    (lv(3, 3, 2, 2, 2), EntryDecision.CONDITIONAL),
    (lv(3, 3, 3, 3, 1), EntryDecision.CONDITIONAL),
])
def test_entry_table(levels, expected):
    assert judge_entry(levels).decision == expected


def test_major_error_blocks_ready():
    assert judge_entry(lv(3, 3, 3, 3, 3), major_error=True).decision == EntryDecision.CONDITIONAL


def test_no_total_score_used():
    # 총점이 같아도 분포에 따라 판정이 다르다 (Z-029)
    a = judge_entry(lv(3, 3, 3, 2, 2)).decision   # 합 13
    b = judge_entry(lv(2, 2, 3, 3, 3)).decision   # 합 13
    assert a != b


def test_support_ceiling():
    assert level_after([]) == Level.INDEPENDENT
    assert level_after([SupportType.VOCAB]) == Level.INDEPENDENT
    assert level_after([SupportType.DIRECTION]) == Level.MINIMAL
    assert level_after([SupportType.DIRECTION, SupportType.DEMO]) == Level.INTENSIVE
