"""품질 게이트 판정과 보고서(JSON·Markdown) 작성."""
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evals.golden import CaseResult

THRESHOLDS = Path(__file__).parent / "thresholds.yaml"
REPORTS = Path(__file__).parent / "reports"

LABEL = {
    "decision_accuracy": "판정 정확도",
    "false_fail_rate": "타당한 답 탈락률",
    "valid_alternative_false_fail_rate": "다른 표현 답 탈락률",
    "disagreement_false_fail_rate": "반대 의견 답 탈락률",
    "false_pass_rate": "미충족 답 통과율",
    "error_accuracy": "대표 오류 정확도",
    "uncertain_rate": "불확실 비율",
    "call_failure_rate": "호출 실패율",
    "avg_latency_sec": "평균 응답 시간(초)",
    "ragas_faithfulness": "Ragas 근거 충실도",
    "ragas_verdict_consistency": "Ragas 근거-판정 일치",
    "ragas_scored_cases": "Ragas 채점 사례 수",
}


def check_gate(metrics: dict, profile: str) -> tuple[bool, dict]:
    rules = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))["profiles"][profile]
    gate = {}
    for name, rule in rules.items():
        v = metrics.get(name)
        if v is None:
            gate[name] = {"value": None, "op": rule["op"], "threshold": rule["value"], "status": "skipped"}
            continue
        ok = v >= rule["value"] if rule["op"] == ">=" else v <= rule["value"]
        gate[name] = {"value": v, "op": rule["op"], "threshold": rule["value"],
                      "status": "pass" if ok else "fail"}
    return all(g["status"] != "fail" for g in gate.values()), gate


def build_report(meta: dict, results: list[CaseResult], metrics: dict, profile: str,
                 analyzer_name: str, content_version: str) -> dict:
    passed, gate = check_gate(metrics, profile)
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "analyzer": analyzer_name, "profile": profile,
        "content_version": content_version, "dataset_version": str(meta.get("version", "")),
        "n_cases": len(results), "metrics": metrics, "gate": gate, "passed": passed,
        "cases": [{
            "id": r.case.id, "bundle": r.case.bundle, "step": r.case.step, "tags": r.case.tags,
            "ref": r.case.ref, "answer": r.case.answer, "choice": r.case.choice,
            "expect": {"pass": r.case.expect_pass, "error": r.case.expect_error},
            "predicted": {"pass": r.predicted_pass, "met": r.diagnosis.met,
                          "error": r.diagnosis.primary_error, "uncertain": r.diagnosis.uncertain},
            "decision_correct": r.decision_correct, "error_correct": r.error_correct,
            "rationale": r.diagnosis.rationale, "latency": round(r.latency, 3),
            "call_error": r.error, "ragas": r.ragas,
        } for r in results],
    }


def to_markdown(rep: dict) -> str:
    lines = [f"# LLM 품질 보고서 — {'✅ 통과' if rep['passed'] else '❌ 미달'}", "",
             f"- 실행: {rep['run_at']} · 분석기: `{rep['analyzer']}` · 기준: `{rep['profile']}`",
             f"- 콘텐츠 {rep['content_version']} · 골든셋 {rep['dataset_version']} · 사례 {rep['n_cases']}개", "",
             "| 지표 | 값 | 기준 | 결과 |", "|---|---|---|---|"]
    for name, v in rep["metrics"].items():
        g = rep["gate"].get(name)
        crit = f"{g['op']} {g['threshold']}" if g else "-"
        st = {"pass": "✅", "fail": "❌", "skipped": "⏭️"}.get(g["status"], "") if g else ""
        lines.append(f"| {LABEL.get(name, name)} | {v if v is not None else '-'} | {crit} | {st} |")
    wrong = [c for c in rep["cases"] if not c["decision_correct"] or c["error_correct"] is False]
    if wrong:
        lines += ["", "## 라벨과 다른 사례", "", "| 사례 | 태그 | 기대 | 예측 | 근거 |", "|---|---|---|---|---|"]
        for c in wrong:
            exp = "충족" if c["expect"]["pass"] else f"미충족({c['expect']['error'] or '-'})"
            pre = "충족" if c["predicted"]["pass"] else f"미충족({c['predicted']['error'] or '-'})"
            lines.append(f"| {c['id']} | {', '.join(c['tags'])} | {exp} | {pre} | {c['ref']} |")
    return "\n".join(lines) + "\n"


def save_report(rep: dict, out_dir: Path = REPORTS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rep["run_at"].replace(":", "").replace("-", "")[:15]
    base = out_dir / f"{stamp}_{rep['profile']}"
    base.with_suffix(".json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    base.with_suffix(".md").write_text(to_markdown(rep), encoding="utf-8")
    (out_dir / f"latest_{rep['profile']}.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return base.with_suffix(".json")
