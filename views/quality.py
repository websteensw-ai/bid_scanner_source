"""교사·운영자: AI 답변 분석 품질 (Ragas + 골든셋).
학생 화면과 무관한 내부 화면이다. 평가는 `python -m evals.run_eval` 로 실행하고, 여기서는 보고서를 본다."""
import json
from pathlib import Path

import streamlit as st

from evals.report import LABEL
from src.services import auth_service
from src.ui.components import _e, card, html, page_header, stat_grid

user = auth_service.require_login("teacher", "admin")
REPORTS = Path(__file__).resolve().parents[1] / "evals" / "reports"

page_header("AI 품질", "답변 분석 AI가 요구사항이 정한 판단을 지키는지, 정답 라벨(골든셋)과 Ragas 지표로 확인해요.",
            eyebrow="🧪 교사·운영자")

files = sorted(REPORTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    st.info("아직 평가 보고서가 없어요. 터미널에서 `python -m evals.run_eval --analyzer llm --ragas` 를 실행하세요.")
    st.stop()

NAMES = {"latest_llm.json": "최신 · 실제 AI 분석기", "latest_demo.json": "최신 · 데모 분석기",
         "baseline_demo.json": "기준선 · 데모 분석기"}
order = sorted(files, key=lambda p: (p.name not in NAMES, list(NAMES).index(p.name) if p.name in NAMES else 0))
f = st.selectbox("보고서", order, format_func=lambda p: NAMES.get(p.name, p.name))
rep = json.loads(f.read_text(encoding="utf-8"))
m = rep["metrics"]


def pct(v):
    return "–" if v is None else f"{v * 100:.0f}"


stat_grid([
    ("✅" if rep["passed"] else "⚠️", "품질 기준", "통과" if rep["passed"] else "미달", ""),
    ("🎯", "판정 정확도", pct(m.get("decision_accuracy")), "%"),
    ("🧩", "다른 표현 답 탈락률", pct(m.get("valid_alternative_false_fail_rate")), "%"),
    ("📎", "Ragas 근거 충실도", pct(m.get("ragas_faithfulness")), "%"),
])
st.caption(f"실행 {rep['run_at'][:16]} · 분석기 `{rep['analyzer']}` · 기준 `{rep['profile']}` · "
           f"콘텐츠 {rep['content_version']} · 골든셋 {rep['dataset_version']} · 사례 {rep['n_cases']}개")
if rep["profile"] == "demo":
    st.warning("데모 분석기는 키워드 단서로 판정하는 시연용이에요. 이 수치는 운영 품질이 아니라 "
               "콘텐츠·엔진 변경을 감시하는 기준선이에요.", icon="ℹ️")

tab_g, tab_c, tab_h = st.tabs(["품질 기준", "사례별 결과", "지표 설명"])
with tab_g:
    rows = []
    for name, v in m.items():
        g = rep["gate"].get(name)
        rows.append({"지표": LABEL.get(name, name), "값": v,
                     "기준": f"{g['op']} {g['threshold']}" if g else "",
                     "결과": {"pass": "✅ 통과", "fail": "❌ 미달", "skipped": "⏭️ 미측정"}.get(g["status"], "")
                     if g else ""})
    st.dataframe(rows, width="stretch", hide_index=True)

with tab_c:
    only_wrong = st.toggle("라벨과 다른 사례만", value=True)
    for c in rep["cases"]:
        wrong = not c["decision_correct"] or c["error_correct"] is False
        if only_wrong and not wrong:
            continue
        exp = "충족" if c["expect"]["pass"] else f"미충족 · {c['expect']['error'] or '-'}"
        pre = "충족" if c["predicted"]["pass"] else f"미충족 · {c['predicted']['error'] or '-'}"
        rg = c.get("ragas") or {}
        with card(f"case_{c['id']}"):
            html(f'<div class="nx-card-meta"><b>{_e(c["id"])}</b><span>{_e(c["bundle"])}/{_e(c["step"])}</span>'
                 f'<span>{_e(", ".join(c["tags"]))}</span><span>근거 {_e(c["ref"])}</span>'
                 f'<span>{"❌" if wrong else "✅"}</span></div>'
                 f'<p style="margin:.5rem 0 .2rem">{_e(c["answer"])}'
                 + (f' <span style="color:var(--text-muted)">[선택: {_e(c["choice"])}]</span>' if c["choice"] else "")
                 + f'</p><p style="margin:0;color:var(--text-secondary)">기대 <b>{_e(exp)}</b> · 예측 <b>{_e(pre)}</b>'
                 f' · 충족 기준 {_e(", ".join(c["predicted"]["met"]) or "-")}</p>'
                 + (f'<p style="margin:.2rem 0 0;color:var(--text-muted);font-size:.88rem">근거: {_e(c["rationale"])}</p>'
                    if c["rationale"] else "")
                 + (f'<p style="margin:.2rem 0 0;color:var(--text-muted);font-size:.88rem">Ragas 충실도 '
                    f'{_e(rg.get("faithfulness"))} · 근거-판정 일치 {_e(rg.get("verdict_consistency"))}'
                    f'{" · " + _e(rg.get("verdict_reason")) if rg.get("verdict_reason") else ""}</p>' if rg else ""))

with tab_h:
    st.markdown("""
| 지표 | 무엇을 보나요 | 관련 요구사항 |
|---|---|---|
| 판정 정확도 | 충족/미충족 판단이 정답 라벨과 같은 비율 | Z-017 |
| 다른 표현 답 탈락률 | 예시와 다르지만 타당한 답을 탈락시킨 비율 (낮을수록 좋음) | P-013, L3-010 |
| 반대 의견 답 탈락률 | 필자에 반대하지만 정확히 읽은 답을 탈락시킨 비율 (0이어야 함) | L1-016, L2-024 |
| 미충족 답 통과율 | 기준을 못 채운 답을 통과시킨 비율 (낮을수록 좋음) | Z-008 |
| 대표 오류 정확도 | 미충족 답에서 오류 유형을 맞힌 비율 — 맞아야 알맞은 첫 질문이 나감 | L1-013, L2-023 |
| Ragas 근거 충실도 | AI가 쓴 판단 근거의 주장들이 제시문·학생 답에 실제로 있는 비율 (Faithfulness) | P-004, P-022 |
| Ragas 근거-판정 일치 | 판단 근거가 판정을 뒷받침하고 의미로 판단했는지 (LLM judge, pass 비율) | P-013, Z-049 |
""")
    st.caption("골든셋: evals/datasets/analyzer_golden.yaml · 기준: evals/thresholds.yaml")
