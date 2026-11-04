import streamlit as st

from src.core.models import FeedbackResult
from src.db.factory import get_repos
from src.services import auth_service
from src.ui.components import (
    _e,
    card,
    chip,
    empty_state,
    html,
    page_header,
    render_feedback,
    stat_grid,
)

user = auth_service.require_login("teacher", "admin")
repos = get_repos()

page_header("교사 대시보드", "과제를 출제하고 학생들의 제출 현황과 AI 첨삭 결과를 관리하세요.",
            eyebrow="🧑‍🏫 Teacher")

submitted = repos.essays.list_submitted()
assignments = repos.assignments.list_open()
scores = [e["feedbacks"][0]["total_score"] for e in submitted if e.get("feedbacks")]

stat_grid([
    ("🗂️", "출제한 과제", f"{len(assignments)}", "개"),
    ("📮", "받은 제출물", f"{len(submitted)}", "편"),
    ("📊", "평균 점수", f"{sum(scores) / len(scores):.0f}" if scores else "–", "점"),
])

html('<div style="height:1.2rem"></div>')
tab_list, tab_new = st.tabs(["제출물 확인", "과제 출제"])

with tab_list:
    if not submitted:
        empty_state("📭", "아직 제출된 논술이 없어요", "학생이 제출하면 여기에서 확인할 수 있어요.")
    for i, e in enumerate(submitted):
        student = (e.get("profiles") or {}).get("full_name") or "-"
        title = (e.get("assignments") or {}).get("title", "-")
        fbs = e.get("feedbacks") or []
        score = f" · {fbs[0]['total_score']}점" if fbs else ""
        with st.expander(f"{student} — {title}{score}"):
            html(f'<div class="nx-card-meta" style="margin-bottom:1rem">{chip(e["status"])}'
                 f'<span>제출일 {_e((e.get("submitted_at") or "")[:10])}</span></div>')
            t1, t2 = st.tabs(["첨삭 결과", "학생 답안"])
            with t1:
                if fbs:
                    render_feedback(FeedbackResult.model_validate(fbs[0]["result"]), key=f"t{i}")
                else:
                    st.info("평가 대기 중이에요.")
            with t2:
                html(f'<div class="nx-prompt" style="white-space:pre-wrap">{_e(e["content"])}</div>')

with tab_new, card("new_assignment"):
    html('<div class="nx-label">새 과제</div>')
    with st.form("new_assignment", clear_on_submit=True, border=False):
        title = st.text_input("과제 제목", placeholder="예) AI와 인간의 창의성")
        prompt = st.text_area("논제", height=180,
                              placeholder="학생에게 제시할 논제를 입력하세요.")
        c1, c2 = st.columns(2)
        min_c = c1.number_input("최소 글자 수", 100, 5000, 800, step=100)
        max_c = c2.number_input("최대 글자 수", 100, 5000, 1600, step=100)
        if st.form_submit_button("과제 출제", type="primary", icon=":material/add:"):
            if not (title and prompt):
                st.warning("제목과 논제를 입력해 주세요.")
            elif min_c > max_c:
                st.warning("최소 글자 수가 최대 글자 수보다 클 수 없어요.")
            else:
                repos.assignments.create(title, prompt, int(min_c), int(max_c), user["id"])
                st.success("과제를 출제했어요.")
