"""콘텐츠 묶음 모델과 로더 (Z-047·Z-050, P-006·P-012, L1-021).

다섯 영역은 독립 프로그램이 아니라 이 공통 모델에 담긴 YAML 콘텐츠로 정의한다.
content/<version>/ 아래에 버전별로 보관하고, 진행 중인 세션은 시작할 때의 버전을
고정해서 쓴다 (P-015·P-025·L3-067).

학생 화면에 보여도 되는 것: Excerpt.label·paragraphs·marks, Step.prompt 등 학생용 문구
내부 전용: Excerpt.source, Step.criteria, Step.errors(첫 질문 제외), 모든 desc/rationale
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content"

ExcerptKind = Literal["lesson", "demo", "independent", "recheck", "practice"]
Status = Literal["draft", "approved", "suspended"]


class SourceInfo(BaseModel):
    """내부 검증 정보. 학생 화면에 절대 출력하지 않는다 (P-018·L1-003)."""
    title: str = ""
    author: str = ""
    location: str = ""
    note: str = ""
    is_sample: bool = True      # 시범용 신규 설계문(실제 저작 인용 아님)


class Excerpt(BaseModel):
    id: str
    label: str                                   # 중립 기호 "(가)"
    paragraphs: list[str]
    marks: dict[int, str] = Field(default_factory=dict)   # 문단 표지 (예: 3 → "필자 해석")
    kind: ExcerptKind = "lesson"
    status: Status = "approved"
    source: SourceInfo = Field(default_factory=SourceInfo)


class StepCriterion(BaseModel):
    """내부 판단 기준 (L1-007: 학생에게 보이지 않음)."""
    id: str
    desc: str
    required: bool = True
    evidence_for: list[str] = Field(default_factory=list)   # C1~C5
    skill: str | None = None                                 # 복습 항목 (예: 1-1)
    signals: list[list[str]] = Field(default_factory=list)   # 데모 분석기용 단서 (그룹별 any)
    absent: list[str] = Field(default_factory=list)          # 데모: 이 표현이 없어야 충족
    expected_choice: str | None = None                       # judge 단계 정답 선택지


class ErrorType(BaseModel):
    id: str
    name: str
    first_question: str          # 승인된 첫 대응 질문 (정답을 알려 주지 않음)
    review_item: str | None = None
    signals: list[list[str]] = Field(default_factory=list)
    on_choice: str | None = None # 이 선택지를 고르면 해당 오류 (judge 단계)
    major: bool = False          # 중대한 오류 (진입 가능 판정 차단)


class Demo(BaseModel):
    """현재 제시문이 아닌 별도 연습문 시범 (L1-015·L2-025·L4-047)."""
    excerpt: str | None = None
    text: str


StepKind = Literal["task", "judge", "outline", "draft", "self_review", "info"]


class Step(BaseModel):
    id: str
    title: str
    kind: StepKind = "task"
    prompt: str
    excerpts: list[str] = Field(default_factory=list)
    sentence: str | None = None                 # 학습용 해석 문장 (원문과 구별 표시, L3-044)
    choices: list[str] = Field(default_factory=list)
    evidence: bool = False                      # 근거 표시 요구
    criteria: list[StepCriterion] = Field(default_factory=list)
    errors: list[ErrorType] = Field(default_factory=list)
    guide: str | None = None                    # 과제 의미 안내 (결론 미포함)
    explanation: str | None = None              # 개념 설명 (집중 지원)
    demo: Demo | None = None
    structure: str | None = None                # 빈 표 등 구조 지원
    vocab: dict[str, str] = Field(default_factory=dict)
    skip_if_met: bool = False                   # 앞 단계에서 기준을 이미 충족했으면 생략 (Z-008)
    only_if_independent: bool = False           # 앞 단계를 독립 수행한 학생에게만 (L2-020)
    independent_check: bool = False             # 독립 확인: 내용 힌트 없음 (L1-018)
    allow_one_direction: bool = False           # 재확인: 방향 질문 1회 허용 → 최소 지원 (S1-137)
    carry_from: list[str] = Field(default_factory=list)   # 앞 산출물 표시 (Z-009). 다른 묶음은 "L4:step"
    prefill_from: str | None = None             # 입력창을 앞 단계 답으로 채움
    max_chars: int | None = None                # 공백 포함, 줄바꿈 제외 (L5-014)
    review_questions: list[str] = Field(default_factory=list)  # 자기검토 질문 (L5-037)
    done_message: str = ""                      # 성공 시 구체적 성취 안내


class Bundle(BaseModel):
    id: str                                     # L1 / S1-가
    kind: Literal["topic", "supplement"] = "topic"
    title: str                                  # 학생용 이름
    goal: str                                   # 오늘의 목표
    intro: str = ""
    order: int = 0
    time_target: str = ""
    steps: list[Step]
    next: str | None = None                     # 다음 학습 주제
    status: Status = "approved"
    # 보충 경로 전용
    parent: str | None = None                   # S1
    path_name: str | None = None                # "중심 판단 재구성"
    criterion: str | None = None                # 재평가할 기준 C1~C5
    trigger_errors: list[str] = Field(default_factory=list)
    trigger_criteria: list[str] = Field(default_factory=list)
    review_items: list[str] = Field(default_factory=list)


class ReviewItem(BaseModel):
    id: str                                     # 1-1
    topic: str                                  # L1
    name: str                                   # 학생용 이름
    skill: str                                  # 기능 설명 (내부)
    explanation: str
    demo: str
    practice: str = ""
    linked_steps: list[str] = Field(default_factory=list)
    stage_errors: list[str] = Field(default_factory=list)   # 본격 단계 관련 오류 (L2-032 등)


class ContentPack(BaseModel):
    version: str
    excerpts: dict[str, Excerpt]
    bundles: dict[str, Bundle]
    review_items: dict[str, ReviewItem]

    def topics(self) -> list[Bundle]:
        return sorted((b for b in self.bundles.values() if b.kind == "topic"), key=lambda b: b.order)

    def supplement_paths(self, parent: str) -> list[Bundle]:
        return [b for b in self.bundles.values() if b.parent == parent]

    def step(self, bundle_id: str, step_id: str) -> Step:
        return next(s for s in self.bundles[bundle_id].steps if s.id == step_id)


def _read_yaml(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def available_versions() -> list[str]:
    return sorted(p.name for p in CONTENT_ROOT.iterdir() if p.is_dir() and (p / "pack.yaml").exists())


def active_version() -> str:
    cfg = CONTENT_ROOT / "active.yaml"
    if cfg.exists():
        return _read_yaml(cfg)["version"]
    return available_versions()[-1]


@lru_cache(maxsize=8)
def load_pack(version: str | None = None) -> ContentPack:
    version = version or active_version()
    root = CONTENT_ROOT / version
    excerpts: dict[str, Excerpt] = {}
    bundles: dict[str, Bundle] = {}
    for f in sorted(root.glob("excerpts*.yaml")):
        for e in _read_yaml(f):
            excerpts[e["id"]] = Excerpt.model_validate(e)
    for f in sorted((root / "bundles").glob("*.yaml")):
        data = _read_yaml(f)
        for b in data if isinstance(data, list) else [data]:
            bundles[b["id"]] = Bundle.model_validate(b)
    review = {r["id"]: ReviewItem.model_validate(r) for r in _read_yaml(root / "review_items.yaml")}
    pack = ContentPack(version=version, excerpts=excerpts, bundles=bundles, review_items=review)
    validate_pack(pack)
    return pack


def validate_pack(pack: ContentPack) -> None:
    """참조 무결성 검사 (L3-066 승인 전 검증의 기계적 부분)."""
    problems = []
    for b in pack.bundles.values():
        ids = [s.id for s in b.steps]
        if len(ids) != len(set(ids)):
            problems.append(f"{b.id}: 단계 id 중복")
        for s in b.steps:
            for ex in s.excerpts + ([s.demo.excerpt] if s.demo and s.demo.excerpt else []):
                if ex not in pack.excerpts:
                    problems.append(f"{b.id}/{s.id}: 없는 제시문 {ex}")
            for c in s.criteria:
                for cr in c.evidence_for:
                    if cr not in {"C1", "C2", "C3", "C4", "C5"}:
                        problems.append(f"{b.id}/{s.id}/{c.id}: 잘못된 기준 {cr}")
                if c.skill and c.skill not in pack.review_items:
                    problems.append(f"{b.id}/{s.id}/{c.id}: 없는 복습 항목 {c.skill}")
            for e in s.errors:
                if e.review_item and e.review_item not in pack.review_items:
                    problems.append(f"{b.id}/{s.id}/{e.id}: 없는 복습 항목 {e.review_item}")
            if s.kind == "judge" and not s.choices:
                problems.append(f"{b.id}/{s.id}: judge 단계에 선택지 없음")
        if b.next and b.next not in pack.bundles:
            problems.append(f"{b.id}: 없는 다음 학습 {b.next}")
        if b.kind == "supplement" and not b.criterion:
            problems.append(f"{b.id}: 보충 경로에 재평가 기준 없음")
    # 재확인·독립 확인 자료는 설명·시범 자료와 겹치면 안 됨 (S1-108·S2-010)
    for b in pack.bundles.values():
        demo_ex = {s.demo.excerpt for s in b.steps if s.demo and s.demo.excerpt}
        for s in b.steps:
            if s.independent_check and set(s.excerpts) & demo_ex:
                problems.append(f"{b.id}/{s.id}: 독립 확인에 시범 자료 사용")
    if problems:
        raise ValueError("콘텐츠 검증 실패:\n" + "\n".join(problems))


def count_chars(text: str) -> int:
    """공백·문장부호 포함, 줄바꿈 제외 글자 수. 화면 표시와 제출 검사에 같은 함수를 쓴다 (L5-015·S5-014)."""
    return len(text.replace("\r", "").replace("\n", ""))
