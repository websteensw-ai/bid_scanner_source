"""골든셋 실행과 결정적 지표.

분석기(LLM·데모)를 정답 라벨이 있는 사례에 돌려, 요구사항이 정한 판단을 얼마나 지키는지 잰다.
Ragas(LLM 판정) 지표는 evals/ragas_judge.py 에서 별도로 계산한다.
"""
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.learning.analyzer import Analyzer, Diagnosis, diagnose
from src.learning.content import ContentPack, load_pack

GOLDEN_PATH = Path(__file__).parent / "datasets" / "analyzer_golden.yaml"


@dataclass
class Case:
    id: str
    bundle: str
    step: str
    answer: str
    evidence: str = ""
    choice: str | None = None
    expect_pass: bool = True
    expect_error: str | None = None
    expect_intent: str = "answer"     # answer / question / answer_request / off_task
    tags: list[str] = field(default_factory=list)
    ref: str = ""


@dataclass
class CaseResult:
    case: Case
    diagnosis: Diagnosis
    predicted_pass: bool
    latency: float
    ragas: dict[str, float | str | None] = field(default_factory=dict)
    error: str | None = None          # 분석 호출 자체가 실패한 경우

    @property
    def intent_correct(self) -> bool:
        return self.diagnosis.intent == self.case.expect_intent

    @property
    def decision_correct(self) -> bool:
        if self.case.expect_intent != "answer":
            return self.intent_correct
        return self.predicted_pass == self.case.expect_pass

    @property
    def error_correct(self) -> bool | None:
        if self.case.expect_intent != "answer" or self.case.expect_pass or self.case.expect_error is None:
            return None
        return self.diagnosis.primary_error == self.case.expect_error


def load_golden(path: Path = GOLDEN_PATH) -> tuple[dict, list[Case]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = []
    for c in data["cases"]:
        exp = c.get("expect", {})
        cases.append(Case(id=c["id"], bundle=c["bundle"], step=c["step"], answer=c["answer"],
                          evidence=c.get("evidence", ""), choice=c.get("choice"),
                          expect_pass=bool(exp.get("pass", exp.get("intent", "answer") == "answer")),
                          expect_error=exp.get("error"), expect_intent=exp.get("intent", "answer"),
                          tags=c.get("tags", []), ref=str(c.get("ref", ""))))
    meta = {k: v for k, v in data.items() if k != "cases"}
    return meta, cases


def validate_cases(cases: list[Case], pack: ContentPack) -> list[str]:
    """골든셋이 현재 콘텐츠와 맞는지 (단계·오류 id·선택지)."""
    problems = []
    for c in cases:
        if c.bundle not in pack.bundles:
            problems.append(f"{c.id}: 없는 묶음 {c.bundle}")
            continue
        steps = {s.id: s for s in pack.bundles[c.bundle].steps}
        step = steps.get(c.step)
        if not step:
            problems.append(f"{c.id}: 없는 단계 {c.step}")
            continue
        if c.expect_error and c.expect_error not in {e.id for e in step.errors}:
            problems.append(f"{c.id}: 단계에 없는 오류 id {c.expect_error}")
        if c.choice and c.choice not in step.choices:
            problems.append(f"{c.id}: 없는 선택지 {c.choice}")
    return problems


def run_cases(cases: list[Case], analyzer: Analyzer, pack: ContentPack | None = None) -> list[CaseResult]:
    pack = pack or load_pack()
    out = []
    for c in cases:
        step = pack.step(c.bundle, c.step)
        excerpts = [pack.excerpts[e] for e in step.excerpts]
        t0 = time.time()
        try:
            d = diagnose(analyzer, step, c.answer, c.evidence, c.choice, excerpts, {})
            err = None
        except Exception as e:      # 분석 실패도 품질 지표로 남긴다
            d, err = Diagnosis(uncertain=True, rationale=""), f"{type(e).__name__}: {e}"
        required = [k.id for k in step.criteria if k.required]
        predicted = d.intent == "answer" and all(r in d.met for r in required)
        out.append(CaseResult(case=c, diagnosis=d, predicted_pass=predicted,
                              latency=time.time() - t0, error=err))
    return out


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def deterministic_metrics(results: list[CaseResult]) -> dict[str, float | None]:
    n = len(results)
    answers = [r for r in results if r.case.expect_intent == "answer"]
    non_answers = [r for r in results if r.case.expect_intent != "answer"]
    exp_pass = [r for r in answers if r.case.expect_pass]
    exp_fail = [r for r in answers if not r.case.expect_pass]
    valid_alt = [r for r in results if "valid_alternative" in r.case.tags]
    disagree = [r for r in results if "disagreement" in r.case.tags]
    err_cases = [r for r in results if r.error_correct is not None]
    return {
        # 판정(충족/미충족)이 라벨과 같은 비율
        "decision_accuracy": _rate(sum(r.decision_correct for r in results), n),
        # 타당한 답을 탈락시킨 비율 — 낮을수록 좋음 (P-013)
        "false_fail_rate": _rate(sum(not r.predicted_pass for r in exp_pass), len(exp_pass)),
        "valid_alternative_false_fail_rate": _rate(sum(not r.predicted_pass for r in valid_alt), len(valid_alt)),
        # 필자 견해에 반대한 정확한 독해를 탈락시킨 비율 (L1-016·L2-024)
        "disagreement_false_fail_rate": _rate(sum(not r.predicted_pass for r in disagree), len(disagree)),
        # 미충족 답을 통과시킨 비율 — 낮을수록 좋음
        "false_pass_rate": _rate(sum(r.predicted_pass for r in exp_fail), len(exp_fail)),
        # 미충족 답에서 대표 오류를 맞힌 비율 (첫 대응 질문이 맞게 나가는지)
        "error_accuracy": _rate(sum(bool(r.error_correct) for r in err_cases), len(err_cases)),
        # 학생 발화 의도(답·질문·정답 요구·무관) 구분 — 엉뚱한 답에 즉시 과제로 되돌리기 위함
        "intent_accuracy": _rate(sum(r.intent_correct for r in results), n),
        "off_task_detection_rate": _rate(sum(r.intent_correct for r in non_answers), len(non_answers)),
        # 과제에 답하려 한 글을 '무관한 말'로 잘못 본 비율 — 0 에 가까워야 함 (학생 답을 무시하게 됨)
        "answer_misflagged_rate": _rate(sum(r.diagnosis.intent != "answer" for r in answers), len(answers)),
        "uncertain_rate": _rate(sum(r.diagnosis.uncertain for r in results), n),
        "call_failure_rate": _rate(sum(r.error is not None for r in results), n),
        "avg_latency_sec": round(sum(r.latency for r in results) / n, 3) if n else None,
    }
