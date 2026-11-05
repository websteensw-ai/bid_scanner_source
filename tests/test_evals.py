"""LLM 품질 평가 체계 테스트.

- 골든셋이 현재 콘텐츠(단계·오류 id·선택지)와 맞는지
- 데모 분석기가 회귀 기준선을 지키는지 (콘텐츠 단서·엔진 변경 감시)
- Ragas judge 호출 경로가 동작하는지 (API 키 없이 가짜 judge 로)
"""
import asyncio
import typing

import pytest
from pydantic import BaseModel

from evals.golden import deterministic_metrics, load_golden, run_cases, validate_cases
from evals.report import build_report, check_gate, to_markdown
from src.learning.analyzer import DemoAnalyzer, Diagnosis
from src.learning.content import load_pack


def test_golden_matches_content():
    _, cases = load_golden()
    assert len(cases) >= 40
    assert validate_cases(cases, load_pack()) == []
    tags = {t for c in cases for t in c.tags}
    assert {"valid_alternative", "disagreement", "unverified_fact"} <= tags


def test_demo_analyzer_regression_gate():
    meta, cases = load_golden()
    results = run_cases(cases, DemoAnalyzer())
    metrics = deterministic_metrics(results)
    passed, gate = check_gate(metrics, "demo")
    assert passed, {k: v for k, v in gate.items() if v["status"] == "fail"}
    # 반대 의견을 독해 오류로 보지 않는 원칙은 데모에서도 지켜야 함 (L1-016)
    assert metrics["disagreement_false_fail_rate"] == 0.0
    rep = build_report(meta, results, metrics, "demo", "demo", "v1")
    assert "LLM 품질 보고서" in to_markdown(rep)


def test_gate_skips_missing_metrics():
    passed, gate = check_gate({"decision_accuracy": 0.95, "false_pass_rate": 0.0,
                               "error_accuracy": 0.9, "call_failure_rate": 0.0,
                               "valid_alternative_false_fail_rate": 0.0,
                               "disagreement_false_fail_rate": 0.0}, "llm")
    assert passed
    assert gate["ragas_faithfulness"]["status"] == "skipped"
    failed, _ = check_gate({"decision_accuracy": 0.5}, "llm")
    assert not failed


# ---------- Ragas 경로 (가짜 judge) ----------
def _fake_value(tp, name):
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Union or str(origin) == "<class 'types.UnionType'>":
        return _fake_value(next(a for a in args if a is not type(None)), name)
    if origin is typing.Literal:
        return args[0]
    if origin is list:
        return [_fake_value(args[0], name)]
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return _fake_instance(tp)
    if tp is int:
        return 1
    if tp is float:
        return 1.0
    if tp is bool:
        return True
    return "pass" if name == "value" else "근거가 제시문에 있음"


def _fake_instance(model):
    return model.model_validate({n: _fake_value(f.annotation, n) for n, f in model.model_fields.items()})


def test_ragas_judge_pipeline_with_fake_llm():
    pytest.importorskip("ragas")
    from ragas.llms.base import InstructorBaseRagasLLM

    from evals.ragas_judge import ragas_metrics, score_results

    class FakeJudge(InstructorBaseRagasLLM):
        prompts: list[str] = []

        def generate(self, prompt, response_model):
            self.prompts.append(prompt)
            return _fake_instance(response_model)

        async def agenerate(self, prompt, response_model):
            return self.generate(prompt, response_model)

    _, cases = load_golden()
    results = run_cases(cases[:3], DemoAnalyzer())
    results[0].diagnosis = Diagnosis(met=["c_judgment"], rationale="학생은 기여에 따른 보상을 썼다.")
    judge = FakeJudge()
    asyncio.run(score_results(results, load_pack(), judge))
    m = ragas_metrics(results)
    assert m["ragas_faithfulness"] == 1.0
    assert m["ragas_verdict_consistency"] == 1.0
    # 판정 프롬프트에 제시문·학생 답·판단 기준이 들어갔는지
    assert any("기여에 따른 보상" in p for p in judge.prompts)
    assert any("판단 기준" in p for p in judge.prompts)
