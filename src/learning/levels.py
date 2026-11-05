"""수준·지원·기록 범주 (공통 기록 스키마).

요구사항 정의서 4장 13번(기록 스키마 통일)에 따라 주제마다 달랐던 지원 범주를
아래 하나의 스키마로 통일한다.

- Level: 3 독립 수행 / 2 최소 지원 후 수행 / 1 집중 지원 후 수행 / 0 미형성 / None 미확인 (Z-024, Z-026)
- SupportType: 어떤 도움을 줬는가. 수준은 질문 횟수가 아니라 실제로 알려 준 내용으로 정한다 (Z-027)
"""
from enum import IntEnum, StrEnum


class Level(IntEnum):
    NOT_FORMED = 0      # 설명·시범 후에도 수행 미확인 (미형성)
    INTENSIVE = 1       # 집중 지원 후 수행
    MINIMAL = 2         # 최소 지원 후 수행
    INDEPENDENT = 3     # 독립 수행


LEVEL_LABEL = {
    Level.INDEPENDENT: "독립 수행",
    Level.MINIMAL: "최소 지원 후 수행",
    Level.INTENSIVE: "집중 지원 후 수행",
    Level.NOT_FORMED: "미형성",
    None: "미확인",
}


def level_label(level: "Level | int | None") -> str:
    return LEVEL_LABEL[None if level is None else Level(level)]


class SupportType(StrEnum):
    """제공한 도움의 종류. 수준 하향 여부는 SUPPORT_CEILING 으로 결정."""
    VOCAB = "vocab"              # 어휘 뜻 (내용 지원 아님, L1-006·L2-008)
    GUIDE = "guide"              # 과제 의미 안내 (결론·이유 미제공, L2-011)
    CONFIRM = "confirm"          # 판단이 불확실해 확인 질문 (Z-010·Z-017)
    DIRECTION = "direction"      # 정답 없는 주의 환기·방향 질문 (최소 지원)
    STRUCTURE = "structure"      # 빈 비교표 등 구조 지원 (최소 지원, L3-020)
    EXPLANATION = "explanation"  # 개념·내용 설명 (집중 지원)
    DEMO = "demo"                # 별도 사례 시범 (집중 지원)


SUPPORT_LABEL = {
    SupportType.VOCAB: "어휘 뜻",
    SupportType.GUIDE: "과제 안내",
    SupportType.CONFIRM: "확인 질문",
    SupportType.DIRECTION: "방향 질문",
    SupportType.STRUCTURE: "구조 지원",
    SupportType.EXPLANATION: "내용 설명",
    SupportType.DEMO: "시범",
}

# 이 지원을 받은 뒤의 수행이 받을 수 있는 최고 수준
SUPPORT_CEILING: dict[SupportType, Level] = {
    SupportType.VOCAB: Level.INDEPENDENT,
    SupportType.CONFIRM: Level.INDEPENDENT,
    SupportType.GUIDE: Level.MINIMAL,
    SupportType.DIRECTION: Level.MINIMAL,
    SupportType.STRUCTURE: Level.MINIMAL,
    SupportType.EXPLANATION: Level.INTENSIVE,
    SupportType.DEMO: Level.INTENSIVE,
}


def level_after(supports: list[SupportType]) -> Level:
    """받은 지원 목록으로 성공 시 부여할 수준. 가장 강한 지원이 상한을 정한다."""
    return min((SUPPORT_CEILING[s] for s in supports), default=Level.INDEPENDENT)


class Criterion(StrEnum):
    """진입 준비 판정 기준 ①~⑤ (Z-026)."""
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"


CRITERION_LABEL = {
    Criterion.C1: "① 중심 판단 파악",
    Criterion.C2: "② 주장과 근거의 구별·연결",
    Criterion.C3: "③ 자기 판단과 이유",
    Criterion.C4: "④ 반론 이해와 대응",
    Criterion.C5: "⑤ 짧은 글 작성과 수정",
}

# 학생용 평이한 이름 (내부 기준 번호를 노출하지 않음, S2-066)
CRITERION_PLAIN = {
    Criterion.C1: "글의 중심 생각 잡기",
    Criterion.C2: "주장과 이유를 구별해 잇기",
    Criterion.C3: "내 판단을 이유와 함께 세우기",
    Criterion.C4: "반론을 이해하고 대응하기",
    Criterion.C5: "짧은 글을 쓰고 스스로 고치기",
}

# 기준과 주로 연결되는 학습 주제·보충
CRITERION_TOPIC = {
    Criterion.C1: "L1", Criterion.C2: "L2", Criterion.C3: "L4",
    Criterion.C4: "L4", Criterion.C5: "L5",
}
CRITERION_SUPPLEMENT = {
    Criterion.C1: "S1", Criterion.C2: "S2", Criterion.C3: "S4",
    Criterion.C4: "S4", Criterion.C5: "S5",
}
