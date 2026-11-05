"""LLM 품질 평가 실행.

예)
  # 데모 분석기 회귀 감시 (키 불필요)
  python -m evals.run_eval --analyzer demo
  # 실제 AI 분석기 + Ragas judge (키 필요, requirements-eval.txt 설치)
  python -m evals.run_eval --analyzer llm --ragas
  # 일부만 빠르게
  python -m evals.run_eval --analyzer llm --ragas --limit 10 --tag valid_alternative

품질 기준(evals/thresholds.yaml)을 못 넘으면 종료 코드 1.
"""
import argparse
import asyncio
import sys

from evals.golden import deterministic_metrics, load_golden, run_cases, validate_cases
from evals.report import save_report, to_markdown
from src.learning.analyzer import DemoAnalyzer, LLMAnalyzer
from src.learning.content import load_pack


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="답변 분석기 품질 평가 (골든셋 + Ragas)")
    p.add_argument("--analyzer", choices=["llm", "demo"], default="llm")
    p.add_argument("--ragas", action="store_true", help="Ragas judge 지표 계산 (LLM 키 필요)")
    p.add_argument("--judge-model", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--tag", default=None, help="이 태그가 붙은 사례만")
    p.add_argument("--no-gate", action="store_true", help="기준 미달이어도 종료 코드 0")
    a = p.parse_args(argv)

    pack = load_pack()
    meta, cases = load_golden()
    problems = validate_cases(cases, pack)
    if problems:
        print("골든셋이 현재 콘텐츠와 맞지 않습니다:\n" + "\n".join(problems), file=sys.stderr)
        return 2
    if a.tag:
        cases = [c for c in cases if a.tag in c.tags]
    if a.limit:
        cases = cases[: a.limit]

    if a.analyzer == "demo":
        analyzer = DemoAnalyzer()
    else:
        from src.ai.factory import get_provider

        analyzer = LLMAnalyzer(get_provider())
    print(f"분석기 {analyzer.name} · 사례 {len(cases)}개 실행 중…", file=sys.stderr)
    results = run_cases(cases, analyzer, pack)
    metrics = deterministic_metrics(results)

    if a.ragas:
        from evals.ragas_judge import build_judge, ragas_metrics, score_results

        judge = build_judge(a.judge_model)
        print("Ragas judge 채점 중…", file=sys.stderr)
        asyncio.run(score_results(results, pack, judge))
        metrics.update(ragas_metrics(results))

    from evals.report import build_report

    rep = build_report(meta, results, metrics, a.analyzer, analyzer.name, pack.version)
    path = save_report(rep)
    print(to_markdown(rep))
    print(f"보고서: {path}", file=sys.stderr)
    return 0 if rep["passed"] or a.no_gate else 1


if __name__ == "__main__":
    sys.exit(main())
