import streamlit as st

from src.core.models import FeedbackResult
from src.db.client import get_supabase
from src.db.repositories import AssignmentRepo, EssayRepo
from src.services import auth_service
from src.ui.components import render_feedback

st.set_page_config(page_title="교사 대시보드", page_icon="🧑‍🏫", layout="wide")
user = auth_service.require_login("teacher", "admin")
db = get_supabase()

st.title("🧑‍🏫 교사 대시보드")
tab_new, tab_list = st.tabs(["과제 출제", "제출물 확인"])

with tab_new, st.form("new_assignment", clear_on_submit=True):
    title = st.text_input("과제 제목")
    prompt = st.text_area("논제", height=200)
    c1, c2 = st.columns(2)
    min_c = c1.number_input("최소 글자수", 100, 5000, 800, step=100)
    max_c = c2.number_input("최대 글자수", 100, 5000, 1600, step=100)
    if st.form_submit_button("출제", type="primary"):
        if title and prompt:
            AssignmentRepo(db).create(title, prompt, int(min_c), int(max_c), user["id"])
            st.success("과제가 등록되었습니다.")
        else:
            st.warning("제목과 논제를 입력하세요.")

with tab_list:
    for e in EssayRepo(db).list_submitted():
        student = (e.get("profiles") or {}).get("full_name") or "-"
        title = (e.get("assignments") or {}).get("title", "-")
        fbs = e.get("feedbacks") or []
        score = f"{fbs[0]['total_score']}점" if fbs else "평가 대기"
        with st.expander(f"{student} · {title} · {score}"):
            st.text(e["content"])
            for fb in fbs:
                st.divider()
                render_feedback(FeedbackResult.model_validate(fb["result"]))
