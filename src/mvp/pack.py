"""문제 패키지·단계 카드·채점표 로더와 공개 범위 필터 (가이드 6장·12장).

엔진은 패키지만 읽고 문제마다 다른 코드를 쓰지 않는다. 화면·AI 로 보낼 자료는
반드시 이 모듈의 view 함수를 거쳐, 공개 범위 밖의 항목이 응답에 아예 실리지 않게 한다.
"""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2] / "content" / "mvp"
SUPPORT_LEVELS = ("independent", "question_then_revised", "scaffolded", "explained_then_restated")
ISSUE_TYPES = ("keyword_only", "case_as_claim", "overclaim", "background_knowledge", "false_identity",
               "false_dichotomy", "not_linked_to_task")


# ---------- 단계 카드 ----------
class Subgoal(BaseModel):
    id: str
    goal: str


class OutputField(BaseModel):
    key: str
    label: str
    min_chars: int = 1


class SelfCheckItem(BaseModel):
    key: str
    label: str


class StageCard(BaseModel):
    id: str
    name: str
    kind: str                      # dialogue / writing / review
    central_question: str
    scope: str = ""
    subgoals: list[Subgoal] = Field(default_factory=list)
    outputs: list[OutputField] = Field(default_factory=list)
    selfcheck: list[SelfCheckItem] = Field(default_factory=list)
    thread_steps: list[str] = Field(default_factory=list)


class Rung(BaseModel):
    rung: int
    name: str
    support: str


class StageCards(BaseModel):
    version: str
    status: str = "draft"
    style: str = "세요"
    limits: dict[str, int]
    ladder: list[Rung]
    forbidden: list[str]
    stages: list[StageCard]

    def get(self, sid: str) -> StageCard:
        return next(s for s in self.stages if s.id == sid)

    def order(self) -> list[str]:
        return [s.id for s in self.stages]

    def support_for(self, rung: int) -> str:
        return self.ladder[min(max(rung, 0), len(self.ladder) - 1)].support


# ---------- 채점표 ----------
class RubricItem(BaseModel):
    code: str
    area: str
    points: float
    priority: int
    name: str
    margin_question: str = ""
    demo_signals: list[list[str]] = Field(default_factory=list)
    demo_negative: list[str] = Field(default_factory=list)


class Area(BaseModel):
    code: str
    name: str
    points: float


class Rubric(BaseModel):
    id: str
    version: str
    levels: dict[int, str]
    areas: list[Area]
    items: list[RubricItem]
    dedupe_rules: list[dict] = Field(default_factory=list)

    @property
    def full_id(self) -> str:
        return f"{self.id}-{self.version}"

    @model_validator(mode="after")
    def _sum(self):
        for a in self.areas:
            got = sum(i.points for i in self.items if i.area == a.code)
            if abs(got - a.points) > 1e-9:
                raise ValueError(f"채점표 영역 {a.code} 배점 합 {got} ≠ {a.points}")
        return self

    def item(self, code: str) -> RubricItem:
        return next(i for i in self.items if i.code == code)


# ---------- 문제 패키지 ----------
class Paragraph(BaseModel):
    id: str
    text: str


class Passage(BaseModel):
    id: str
    paragraphs: list[Paragraph]


class Exam(BaseModel):
    title: str
    passages: list[Passage]
    prompt: str
    conditions: list[str]


class ErrorPattern(BaseModel):
    code: str
    issue_type: str
    stages: list[str]
    signal: str
    demo_signals: list[str] = Field(default_factory=list)
    first_question: str
    purpose: str = ""
    rubric_refs: list[str] = Field(default_factory=list)


class Override(BaseModel):
    criterion: str
    demo_signals: list[list[str]] = Field(default_factory=list)
    first_question: str = ""


class Exemplar(BaseModel):
    stage: str
    subgoal: str
    tags: list[str] = Field(default_factory=list)
    is_example_only: bool = True
    turns: list[dict]


class ModelAnswer(BaseModel):
    id: str
    note: str
    text: str


class Pack(BaseModel):
    meta: dict
    visibility: dict[str, list[str]]
    exam: Exam
    required_tasks: list[dict]
    non_required_tasks: list[str] = Field(default_factory=list)
    passage_roles: list[dict]
    key_concepts: list[dict]
    explanation_criteria: dict[str, str]
    error_patterns: list[ErrorPattern]
    stage_overrides: dict[str, Override]
    exemplars: list[Exemplar] = Field(default_factory=list)
    model_answers: list[ModelAnswer] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def version(self) -> str:
        return self.meta["version"]

    @property
    def max_chars(self) -> int:
        return int(self.meta["limits"]["max_chars"])

    @model_validator(mode="after")
    def _check(self):
        for e in self.error_patterns:
            if e.issue_type not in ISSUE_TYPES:
                raise ValueError(f"오류 유형 {e.code}: 알 수 없는 issue_type {e.issue_type}")
        ids = [p.id for ps in self.exam.passages for p in ps.paragraphs]
        if len(ids) != len(set(ids)):
            raise ValueError("문단 ID 가 중복됩니다")
        return self

    def paragraph_ids(self) -> set[str]:
        return {p.id for ps in self.exam.passages for p in ps.paragraphs}

    # ----- 공개 범위 view (12장) -----
    def view_student(self) -> dict:
        """학생 화면: 시험지 원문·논제·조건만."""
        return {"meta": {k: self.meta[k] for k in ("id", "version", "limits")}, "exam": self.exam}

    def view_tutor(self, stage: str, subgoal: str | None) -> dict:
        """문답 튜터: 이 단계 허용분만. 예시답안·채점표는 넣지 않는다."""
        return {
            "exam": self.exam,
            "required_tasks": self.required_tasks,
            "passage_roles": self.passage_roles,
            "key_concepts": [c for c in self.key_concepts if stage in c.get("stages", [])],
            "explanation_criteria": self.explanation_criteria,
            "error_patterns": [e for e in self.error_patterns if stage in e.stages],
            "overrides": {k: v for k, v in self.stage_overrides.items() if k.startswith(f"S{stage}-")},
            "exemplars": [x for x in self.exemplars if x.stage == stage and (subgoal is None or x.subgoal == subgoal)][:2],
        }

    def view_grader(self) -> dict:
        return {"exam": self.exam, "required_tasks": self.required_tasks,
                "explanation_criteria": self.explanation_criteria, "model_answers": self.model_answers,
                "error_patterns": self.error_patterns}


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache
def stage_cards() -> StageCards:
    return StageCards.model_validate(_read(ROOT / "stage_cards.yaml"))


@lru_cache
def load_problem(pack_id: str = "BASIC-Q1") -> tuple[Pack, Rubric]:
    d = ROOT / "packs" / pack_id
    pack = Pack.model_validate(_read(d / "pack.yaml"))
    rubric = Rubric.model_validate(_read(d / "rubric.yaml"))
    cards = stage_cards()
    known = {sg.id for s in cards.stages for sg in s.subgoals}
    missing = known - set(pack.stage_overrides)
    if missing:
        raise ValueError(f"{pack_id}: stage_overrides 에 없는 하위 목표 {sorted(missing)}")
    for code in {r for e in pack.error_patterns for r in e.rubric_refs}:
        rubric.item(code)
    return pack, rubric


@lru_cache
def reflection_items() -> dict:
    return _read(ROOT / "reflection.yaml")


def available_problems() -> list[str]:
    return sorted(p.name for p in (ROOT / "packs").iterdir() if (p / "pack.yaml").exists())


def guide_pages() -> list[tuple[str, str]]:
    return [(p.stem, p.read_text(encoding="utf-8")) for p in sorted((ROOT / "guide").glob("*.md"))]
