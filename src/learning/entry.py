"""진입 준비 판정 (Z-026~Z-030, S2-057~S2-060).

요구사항 정의서 4장 14번 권고에 따라 판정표를 이 한 곳에 정리하고 테스트로 고정한다.
4장 4번(판정 명칭 통일)에 따라 명칭은 Z-028 의 네 가지로 통일한다.

규칙 (위에서부터 먼저 해당하는 것):
1. 증거가 부족한 기준(미확인)이 있으면 → 판정 보류—확인 필요
2. ①·② 중 하나라도 1 이하, 또는 어느 기준이든 0, 또는 ③~⑤ 중 두 기준 이상이 1
   → 집중 보충 후 재확인
3. 다섯 기준 모두 2 이상 + ①·② 포함 세 기준 이상이 3 + 중대한 오류 없음 → 진입 가능
4. 그 밖에 다섯 기준 모두 2 이상, 또는 ①·②가 2 이상이고 ③~⑤ 중 한 기준만 1 → 조건부 진입

총점·출석·완료 여부로 판정하지 않는다 (Z-029).
"""
from dataclasses import dataclass, field
from enum import StrEnum

from src.learning.levels import CRITERION_PLAIN, Criterion, Level


class EntryDecision(StrEnum):
    READY = "진입 가능"
    CONDITIONAL = "조건부 진입"
    SUPPLEMENT = "집중 보충 후 재확인"
    HOLD = "판정 보류—확인 필요"


STUDENT_MESSAGE = {
    EntryDecision.READY: "다섯 가지 학습에서 해낸 것을 바탕으로 초급 단계부터 이어 갈 수 있어요. "
                         "지금까지 쓴 답과 기록은 본격 학습에서도 그대로 이어져요.",
    EntryDecision.CONDITIONAL: "본격 학습을 시작할 수 있어요. 아직 도움이 필요한 부분은 "
                               "학습 중에 질문으로 함께 짚고, 원하면 복습을 골라 볼 수 있어요.",
    EntryDecision.SUPPLEMENT: "본격 학습 전에 꼭 필요한 부분을 짧게 보충하고 다시 확인해요. "
                              "지금까지 해낸 것은 그대로 남아 있어요.",
    EntryDecision.HOLD: "아직 판단할 근거가 조금 부족해요. 짧은 확인 과제로 한 번 더 살펴볼게요.",
}

CORE = (Criterion.C1, Criterion.C2)
OTHERS = (Criterion.C3, Criterion.C4, Criterion.C5)


@dataclass
class EntryResult:
    decision: EntryDecision
    reasons: list[str] = field(default_factory=list)       # 내부용 판정 이유
    focus: list[Criterion] = field(default_factory=list)   # 보충·확인이 필요한 기준

    @property
    def student_message(self) -> str:
        return STUDENT_MESSAGE[self.decision]


def judge_entry(levels: dict[Criterion, Level | int | None], major_error: bool = False) -> EntryResult:
    lv = {c: (None if levels.get(c) is None else Level(levels[c])) for c in Criterion}

    missing = [c for c in Criterion if lv[c] is None]
    if missing:
        return EntryResult(EntryDecision.HOLD,
                           [f"{', '.join(CRITERION_PLAIN[c] for c in missing)}: 증거 부족(미확인)"],
                           missing)

    core_low = [c for c in CORE if lv[c] <= Level.INTENSIVE]
    zeros = [c for c in Criterion if lv[c] == Level.NOT_FORMED]
    others_one = [c for c in OTHERS if lv[c] == Level.INTENSIVE]
    if core_low or zeros or len(others_one) >= 2:
        focus = list(dict.fromkeys(core_low + zeros + (others_one if len(others_one) >= 2 else [])))
        reasons = []
        if core_low:
            reasons.append("핵심 기준(①·②) 중 집중 지원이 필요한 기준이 있음")
        if zeros:
            reasons.append("설명·시범 후에도 수행이 확인되지 않은 기준이 있음")
        if len(others_one) >= 2:
            reasons.append("③~⑤ 중 두 기준 이상이 집중 지원 후 수행")
        return EntryResult(EntryDecision.SUPPLEMENT, reasons, focus)

    threes = [c for c in Criterion if lv[c] == Level.INDEPENDENT]
    all_two = all(lv[c] >= Level.MINIMAL for c in Criterion)
    if all_two and len(threes) >= 3 and all(c in threes for c in CORE) and not major_error:
        return EntryResult(EntryDecision.READY,
                           ["다섯 기준 모두 2 이상, ①·② 포함 세 기준 이상이 독립 수행"])

    focus = [c for c in Criterion if lv[c] < Level.INDEPENDENT]
    if all_two:
        reason = "다섯 기준 모두 2 이상이나 독립 수행 조건(①·② 포함 3개 이상 3)에 못 미침"
        if major_error:
            reason = "다섯 기준 모두 2 이상이나 중대한 오류가 남아 있음"
        return EntryResult(EntryDecision.CONDITIONAL, [reason], focus)
    # 여기 도달 = ①·② ≥2, 0 없음, ③~⑤ 중 정확히 하나가 1
    return EntryResult(EntryDecision.CONDITIONAL,
                       ["①·②는 2 이상, ③~⑤ 중 한 기준만 집중 지원 후 수행"], focus)
