"""학습 상태와 기록 (Z-025·Z-048, L1-025, S1-002·S2-044~048).

학생 한 명의 모든 학습 기록을 LearnerState 하나에 담아 JSON 으로 저장한다.
- 최초 답과 수정 답은 덮어쓰지 않고 Attempt 로 모두 남긴다
- 제공한 도움은 SupportRecord 로 시점·종류·내용을 남긴다
- 기준별 판단은 근거 응답·지원·자료 버전과 함께 CriterionRecord 로 남긴다
"""
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.learning.levels import SupportType


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Message(BaseModel):
    role: Literal["tutor", "student", "system"]
    text: str
    kind: str = ""              # answer / direction / explanation / demo / done ...
    ts: str = Field(default_factory=now)


class Attempt(BaseModel):
    text: str
    evidence: str = ""
    choice: str | None = None
    kind: Literal["first", "revised"] = "first"
    supports_before: list[SupportType] = Field(default_factory=list)
    ts: str = Field(default_factory=now)
    met: list[str] = Field(default_factory=list)       # 분석 결과 (내부)
    error: str | None = None
    rationale: str = ""


class SupportRecord(BaseModel):
    type: SupportType
    point: str = ""             # 판단점 (오류 id 또는 기준 id)
    text: str = ""
    ts: str = Field(default_factory=now)


class StepState(BaseModel):
    step_id: str
    status: Literal["active", "done", "skipped"] = "active"
    attempts: list[Attempt] = Field(default_factory=list)
    supports: list[SupportRecord] = Field(default_factory=list)
    directions: dict[str, int] = Field(default_factory=dict)   # 판단점별 방향 질문 수
    explained: bool = False
    demoed: bool = False
    confirms: int = 0
    level: int | None = None                # 이 단계 결과 수준 (None=미확인)
    unresolved: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    active_seconds: float = 0.0             # 학생 활동 시간 (Z-020)
    ai_wait_seconds: float = 0.0            # AI 대기 시간 (별도 집계)
    shown_at: str = Field(default_factory=now)


class SessionState(BaseModel):
    key: str                                # 세션 식별자 (bundle id)
    bundle_id: str
    version: str                            # 고정된 콘텐츠 버전
    status: Literal["active", "paused", "done"] = "active"
    step_idx: int = 0
    steps: dict[str, StepState] = Field(default_factory=dict)
    met: dict[str, int] = Field(default_factory=dict)      # 충족한 단계 기준 id → 수준
    outputs: dict[str, str] = Field(default_factory=dict)  # 단계 id → 최종 답 (후속 활동에서 재사용)
    first_outputs: dict[str, str] = Field(default_factory=dict)
    errors_seen: list[str] = Field(default_factory=list)
    major_error: bool = False
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    result: dict[str, int | None] = Field(default_factory=dict)  # 기준 C1~C5 → 수준 (이 세션 증거)


class CriterionRecord(BaseModel):
    level: int | None = None
    source: str = ""                        # 근거 세션/단계
    evidence: str = ""                      # 근거가 된 학생 응답 (요약)
    supports: list[str] = Field(default_factory=list)
    version: str = ""
    ts: str = Field(default_factory=now)
    by: Literal["system", "teacher"] = "system"
    note: str = ""


class Flag(BaseModel):
    """교사·운영자 검토 요청 (Z-036·Z-038·L1-019)."""
    kind: Literal["uncertain", "repeat_difficulty", "dispute", "not_confirmed", "content"]
    source: str
    detail: str
    ts: str = Field(default_factory=now)
    resolved: bool = False


class Event(BaseModel):
    type: str
    source: str
    payload: dict = Field(default_factory=dict)
    ts: str = Field(default_factory=now)


class ReviewRecord(BaseModel):
    """선택 복습 기록: 추천·열람·수행을 구분 (L1-035·L2-041)."""
    item: str
    reason: str
    action: Literal["recommended", "saved", "opened", "practiced"]
    origin: str = ""                        # 출발 위치 (Z-041)
    ts: str = Field(default_factory=now)


class LearnerState(BaseModel):
    student_id: str
    sessions: dict[str, SessionState] = Field(default_factory=dict)
    criteria: dict[str, CriterionRecord] = Field(default_factory=dict)
    criteria_history: list[tuple[str, CriterionRecord]] = Field(default_factory=list)
    entry: list[dict] = Field(default_factory=list)
    supplements_done: list[str] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    reviews: list[ReviewRecord] = Field(default_factory=list)

    def log(self, type_: str, source: str, **payload) -> None:
        self.events.append(Event(type=type_, source=source, payload=payload))
