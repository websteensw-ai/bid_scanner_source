import streamlit as st

from src.core.models import FeedbackResult
from src.db.factory import get_repos
from src.services import auth_service
from src.ui.components import render_feedback

st.set_page_config(page_title="제출 내역", page_icon="📋", layout="wide")
user = auth_service.require_login("student")

st.title("📋 제출 내역")
essays = get_repos().essays.list_by_student(user["id"])
if not essays:
    st.info("제출한 논술이 없습니다.")

for e in essays:
    title = (e.get("assignments") or {}).get("title", "(삭제된 과제)")
    with st.expander(f"{title} · {e['status']}"):
        st.text(e["content"])
        for fb in e.get("feedbacks") or []:
            st.divider()
            render_feedback(FeedbackResult.model_validate(fb["result"]))
