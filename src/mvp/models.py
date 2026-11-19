"""6단계 회차(Attempt) 기록 모델 — 가이드 13장 데이터 모델.

모든 학습 기록은 추가만 하고 덮어쓰지 않는다. 수정은 새 항목(버전)을 만들고 이전 항목을 가리킨다.
회차 하나가 LearnerState.mvp 에 JSON 으로 저장된다 (web/store.py 가 그대로 저장).
"""
from typing import Literal

from pydantic import BaseModel, Field

from src.learning.state import now

StageStatus = Literal["locked", "in_progress", "summarizing", "judging", "completed", "flagged"]
SubgoalState = Literal["met", "partial", "not_yet", "skipped"]
DraftKind = Literal["independent", "selfchecked", "pre_revision", "submitted", "final"]
WritingCondition = Literal["independent_after_support", "ai_supported", "teacher_supported",
                           "interrupted_then_supplemented"]
AnnotationStatus = Literal["active", "withdrawn", "adjusted", "resolved", "unresolved"]


class TutorJudgment(BaseModel):
    """튜터의 구조화 판단 (5-4). 학생에게 보이지 않는다."""
    subgoal_id: str | None = None
    subgoal_status: SubgoalState = "not_yet"
    subgoals_met: list[str] = Field(default_factory=list)   # 이번 발화로 함께 확인된 하위목표
    issue_type: str | None = None
    error_code: str | None = None
    student_quote: str = ""
    passage_refs: list[str] = Field(default_factory=list)
    scaffold_level: int = 0
    support_level_so_far: str = "independent"
    thinking_change: dict | None = None        # {before, after, note}
    handoff_note: str = ""
    flag_teacher: bool = False
    intent: str = "answer"


class Turn(BaseModel):
    role: Literal["tutor", "student", "system"]
    text: str
    judgment: TutorJudgment | None = None
    prompt_version: str = ""
    model: str = ""
    check: dict = Field(default_factory=dict)  # 응답 검사 결과
    regenerated: int = 0
    rejected_drafts: list[str] = Field(default_factory=list)   # 불합격 초안 (학생에게 보이지 않음)
    ts: str = Field(default_factory=now)


class SubgoalRecord(BaseModel):
    status: SubgoalState = "not_yet"
    support: str = "independent"
    turns: int = 0
    evidence_turn: int | None = None


class OutputValue(BaseModel):
    value: str
    source: Literal["student_turn", "typed"] = "typed"
    turn_index: int | None = None


class StageOutput(BaseModel):
    version: int
    fields: dict[str, OutputValue]
    verdict: Literal["pass", "fail", "pending"] = "pending"
    verdict_note: str = ""
    ts: str = Field(default_factory=now)


class StageRun(BaseModel):
    stage: str
    status: StageStatus = "locked"
    subgoal_idx: int = 0
    subgoals: dict[str, SubgoalRecord] = Field(default_factory=dict)
    rung: int = 0
    support: str = "independent"
    answer_requests: int = 0
    turns: list[Turn] = Field(default_factory=list)
    outputs: list[StageOutput] = Field(default_factory=list)
    teacher_override: str = ""
    verdict: str | None = None       # ready / ready_with_support / needs_support / unconfirmed (단계 판정)
    started_at: str | None = None
    finished_at: str | None = None
    last_seen: str | None = None

    def student_turns(self) -> int:
        return sum(1 for t in self.turns if t.role == "student")


class ThinkingChange(BaseModel):
    stage: str
    before: str
    after: str
    note: str = ""
    turn_index: int | None = None
    final_link: str = ""
    ts: str = Field(default_factory=now)


class DraftVersion(BaseModel):
    id: str
    kind: DraftKind
    body: str
    chars: int
    cells: int
    condition: WritingCondition = "independent_after_support"
    frozen: bool = True
    same_as: str | None = None                 # 수정 없이 저장된 선행 수정본
    ts: str = Field(default_factory=now)


class WritingEvent(BaseModel):
    kind: Literal["paste", "help", "interrupt", "accessibility", "start", "autosave"]
    detail: str = ""
    size: int = 0
    ts: str = Field(default_factory=now)


class SelfCheckEntry(BaseModel):
    key: str
    start: int | None = None
    end: int | None = None
    quote: str = ""
    judgment: Literal["problem", "keep"]
    reason: str = ""


class SelfCheck(BaseModel):
    draft_id: str
    entries: list[SelfCheckEntry]
    confident: str
    uncertain: str
    ts: str = Field(default_factory=now)


class EvalItem(BaseModel):
    code: str
    level: int | None                          # None = 판정 보류 (0점과 구분)
    evidence: list[dict] = Field(default_factory=list)   # [{start, end, quote}]
    reason: str = ""
    error_code: str | None = None
    confidence: str = "medium"
    score: float | None = None
    review_recommended: bool = False


class Evaluation(BaseModel):
    id: str
    draft_id: str
    rubric_version: str
    evaluator: str                              # ai:<model> / teacher:<id>
    items: list[EvalItem]
    area_scores: dict[str, float]
    total: float
    provisional: bool = False
    over_chars: int = 0
    replaces: str | None = None
    note: str = ""
    runs: int = 1
    ts: str = Field(default_factory=now)


class ThreadTurn(BaseModel):
    role: Literal["tutor", "student"]
    text: str
    step: int = 0
    ts: str = Field(default_factory=now)


class Annotation(BaseModel):
    number: int
    rubric_refs: list[str]
    anchor: dict                                # {draft_id, start, end, quote}
    mark_type: str = "underline"
    nature: Literal["correction", "optional_improvement", "strength"] = "correction"
    margin_note: str = ""
    status: AnnotationStatus = "active"
    shown: bool = True                          # 상위 2~3개만 표시, 나머지 '더 보기'
    decision: Literal["accept", "partial", "reject"] | None = None
    decision_reason: str = ""
    revision_link: dict | None = None
    support_steps: list[str] = Field(default_factory=list)
    thread: list[ThreadTurn] = Field(default_factory=list)
    thread_step: int = 0
    stalls: int = 0
    history: list[dict] = Field(default_factory=list)


class Appeal(BaseModel):
    target: str                                 # eval:<code> / ann:<number>
    reason: str
    status: Literal["received", "reviewing", "done", "held"] = "received"
    result: str = ""
    ts: str = Field(default_factory=now)


class Reflection(BaseModel):
    version: str
    status: Literal["unanswered", "draft", "submitted", "skipped"] = "unanswered"
    answers: dict[str, object] = Field(default_factory=dict)
    first_answers: dict[str, object] | None = None
    first_submitted_at: str | None = None
    updated_at: str | None = None


class Alert(BaseModel):
    kind: Literal["stall", "grading_mismatch", "paste", "ai_copy", "danger", "appeal", "unresolved"]
    stage: str
    detail: str
    status: Literal["received", "reviewing", "done", "held"] = "received"
    note: str = ""
    ts: str = Field(default_factory=now)


class Audit(BaseModel):
    who: str
    action: str
    target: str = ""
    ts: str = Field(default_factory=now)


class MvpAttempt(BaseModel):
    id: str
    pack_id: str
    pack_version: str
    rubric_version: str
    cards_version: str
    mode: Literal["deep", "compressed", "exam"] = "deep"
    status: Literal["active", "done"] = "active"
    onboarded: bool = False
    stages: dict[str, StageRun] = Field(default_factory=dict)
    current: str = "0"
    thinking: list[ThinkingChange] = Field(default_factory=list)
    temp_draft: str = ""
    temp_saved_at: str | None = None
    drafts: list[DraftVersion] = Field(default_factory=list)
    events: list[WritingEvent] = Field(default_factory=list)
    selfcheck: SelfCheck | None = None
    selfcheck_result: dict[str, str] = Field(default_factory=dict)
    writing_started: str | None = None
    writing_seconds: float = 0.0
    evaluations: list[Evaluation] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    diagnosis: dict = Field(default_factory=dict)        # 6-1 짧은 자기진단
    review_phase: Literal["diagnose", "results", "threads", "revise", "compare", "done"] = "diagnose"
    appeals: list[Appeal] = Field(default_factory=list)
    reflection: Reflection | None = None
    next_check_question: str = ""
    alerts: list[Alert] = Field(default_factory=list)
    teacher_notes: list[dict] = Field(default_factory=list)
    audit: list[Audit] = Field(default_factory=list)
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None

    def draft(self, kind: str) -> DraftVersion | None:
        return next((d for d in reversed(self.drafts) if d.kind == kind), None)

    def draft_by_id(self, did: str) -> DraftVersion | None:
        return next((d for d in self.drafts if d.id == did), None)

    def latest_eval(self, draft_id: str) -> Evaluation | None:
        return next((e for e in reversed(self.evaluations) if e.draft_id == draft_id), None)
