"""Ragas 로 분석기 응답의 질을 LLM 판정(judge)으로 잰다.

- faithfulness (ragas.metrics.collections.Faithfulness)
    분석기가 남긴 판단 근거(rationale)의 각 주장이 제시문·학생 답·판단 기준에 실제로 있는가.
    원문에 없는 내용을 귀속하거나 학생 답을 지어내지 않는지 본다 (P-004·P-022).
- verdict_consistency (ragas.metrics.DiscreteMetric, pass/fail)
    판단 근거가 판정 결과(충족 기준·대표 오류)를 실제로 뒷받침하고, 의미로 판단했는가 (P-013).

judge 모델은 분석기와 다른 모델을 권장한다 (같은 모델의 자기 평가 편향 완화).
EVAL_JUDGE_MODEL 환경변수로 바꿀 수 있다.
"""
import asyncio
import math

from evals.golden import CaseResult
from src.learning.content import ContentPack

VERDICT_PROMPT = """당신은 논술 기초 과정 답변 분석기의 판정을 검수하는 교사입니다.

[과제]
{task}

[판단 기준]
{criteria}

[학생 답]
{answer}

[분석기 판정]
{verdict}

[분석기 판단 근거]
{rationale}

다음을 모두 만족하면 pass, 하나라도 어기면 fail 로 답하세요.
1. 판단 근거가 판정 결과(충족한 기준, 대표 오류)를 실제로 뒷받침하고 서로 모순되지 않는다.
2. 예시 문구와의 일치가 아니라 학생 답의 의미로 판단했다.
3. 학생이 필자 견해에 동의하지 않는다는 이유만으로 감점하지 않았다.
4. 제시문에 없는 내용을 근거로 삼지 않았다."""


def build_judge(model: str | None = None):
    """설정된 제공자(Claude/OpenAI)로 Ragas judge LLM 을 만든다."""
    import os

    from ragas.llms import llm_factory

    from src.core.config import get_settings

    s = get_settings()
    model = model or os.getenv("EVAL_JUDGE_MODEL") or s.eval_judge_model
    if s.ai_provider == "claude":
        from anthropic import AsyncAnthropic

        if not s.anthropic_api_key:
            raise RuntimeError("Ragas judge 에 ANTHROPIC_API_KEY 가 필요합니다.")
        return llm_factory(model or "claude-opus-5-5", provider="anthropic",
                           client=AsyncAnthropic(api_key=s.anthropic_api_key), max_tokens=2048)
    from openai import AsyncOpenAI

    if not s.openai_api_key:
        raise RuntimeError("Ragas judge 에 OPENAI_API_KEY 가 필요합니다.")
    return llm_factory(model or "gpt-4o", provider="openai", client=AsyncOpenAI(api_key=s.openai_api_key))


def _inputs(r: CaseResult, pack: ContentPack) -> dict:
    step = pack.step(r.case.bundle, r.case.step)
    passages = ["\n".join([pack.excerpts[e].label, *pack.excerpts[e].paragraphs]) for e in step.excerpts]
    criteria = "\n".join(f"- {c.id}: {c.desc}" for c in step.criteria)
    errors = "\n".join(f"- {e.id}: {e.name}" for e in step.errors)
    answer = r.case.answer + (f"\n(근거 표시: {r.case.evidence})" if r.case.evidence else "") \
        + (f"\n(선택: {r.case.choice})" if r.case.choice else "")
    task = step.prompt + (f"\n학습용 해석 문장: {step.sentence}" if step.sentence else "")
    verdict = (f"충족 기준: {', '.join(r.diagnosis.met) or '없음'} / "
               f"대표 오류: {r.diagnosis.primary_error or '없음'} / 불확실: {r.diagnosis.uncertain}")
    return {
        "task": task, "criteria": criteria + ("\n오류 유형:\n" + errors if errors else ""),
        "answer": answer, "verdict": verdict, "rationale": r.diagnosis.rationale,
        "contexts": passages + [f"학생 답: {answer}", f"판단 기준:\n{criteria}"],
    }


async def _score_one(r: CaseResult, pack: ContentPack, faith, verdict_metric, llm, sem) -> None:
    if not r.diagnosis.rationale.strip() or r.error:
        r.ragas = {"faithfulness": None, "verdict_consistency": None, "note": "판단 근거 없음"}
        return
    x = _inputs(r, pack)
    async with sem:
        try:
            f = await faith.ascore(user_input=f"{x['task']}\n학생 답: {x['answer']}",
                                   response=x["rationale"], retrieved_contexts=x["contexts"])
            fv = None if f.value is None or (isinstance(f.value, float) and math.isnan(f.value)) else float(f.value)
        except Exception as e:  # judge 오류는 사례별로 기록하고 계속
            fv, r.ragas["faithfulness_error"] = None, str(e)[:200]
        try:
            v = await verdict_metric.ascore(llm=llm, task=x["task"], criteria=x["criteria"], answer=x["answer"],
                                            verdict=x["verdict"], rationale=x["rationale"])
            vv = v.value
            r.ragas["verdict_reason"] = (getattr(v, "reason", None) or "")[:300]
        except Exception as e:
            vv, r.ragas["verdict_error"] = None, str(e)[:200]
    r.ragas.update({"faithfulness": fv, "verdict_consistency": vv})


async def score_results(results: list[CaseResult], pack: ContentPack, llm, concurrency: int = 4) -> None:
    from ragas.metrics import DiscreteMetric
    from ragas.metrics.collections import Faithfulness

    faith = Faithfulness(llm=llm)
    verdict_metric = DiscreteMetric(name="verdict_consistency", allowed_values=["pass", "fail"],
                                    prompt=VERDICT_PROMPT)
    sem = asyncio.Semaphore(concurrency)
    await asyncio.gather(*(_score_one(r, pack, faith, verdict_metric, llm, sem) for r in results))


def ragas_metrics(results: list[CaseResult]) -> dict[str, float | None]:
    fs = [r.ragas.get("faithfulness") for r in results if r.ragas.get("faithfulness") is not None]
    vs = [r.ragas.get("verdict_consistency") for r in results if r.ragas.get("verdict_consistency")]
    return {
        "ragas_faithfulness": round(sum(fs) / len(fs), 4) if fs else None,
        "ragas_verdict_consistency": round(sum(v == "pass" for v in vs) / len(vs), 4) if vs else None,
        "ragas_scored_cases": len(fs),
    }
