import streamlit as st

from src.core.models import FeedbackResult
from src.db.factory import get_repos
from src.services import auth_service
from src.ui.components import _e, chip, empty_state, html, page_header, render_feedback

user = auth_service.require_login("student")
st.session_state.pop("selected_assignment", None)

page_header("첨삭 기록", "지난 논술과 AI 피드백을 다시 보며 성장 과정을 확인하세요.",
            eyebrow="📚 History")

essays = [e for e in get_repos().essays.list_by_student(user["id"]) if e["status"] != "draft"]
if not essays:
    empty_state("📭", "아직 제출한 논술이 없어요", "논술을 제출하면 AI 첨삭 결과가 여기에 쌓여요.")
    st.stop()

for i, e in enumerate(essays):
    title = (e.get("assignments") or {}).get("title", "(삭제된 과제)")
    fbs = e.get("feedbacks") or []
    score = f" · {fbs[0]['total_score']}점" if fbs else ""
    date = (e.get("submitted_at") or "")[:10]
    with st.expander(f"{title}{score}", expanded=i == 0):
        html(f'<div class="nx-card-meta" style="margin-bottom:1rem">{chip(e["status"])}'
             f'<span>제출일 {_e(date)}</span></div>')
        tab_fb, tab_txt = st.tabs(["첨삭 결과", "내 답안"])
        with tab_fb:
            if fbs:
                render_feedback(FeedbackResult.model_validate(fbs[0]["result"]), key=f"h{i}")
            else:
                st.info("AI가 평가 중이에요. 잠시 후 다시 확인해 주세요.")
        with tab_txt:
            html(f'<div class="nx-prompt" style="white-space:pre-wrap;background:var(--surface);'
                 f'border:1px solid var(--border);border-radius:12px;padding:1.2rem 1.4rem">'
                 f'{_e(e["content"])}</div>')
