import streamlit as st

from src.core.config import get_settings
from src.db.client import get_supabase
from src.db.repositories import AssignmentRepo, EssayRepo
from src.services import auth_service, feedback_service
from src.ui.components import char_counter, render_feedback

st.set_page_config(page_title="논술 작성", page_icon="✍️", layout="wide")
user = auth_service.require_login("student")
db = get_supabase()

st.title("✍️ 논술 작성")

assignments = AssignmentRepo(db).list_open()
if not assignments:
    st.info("아직 등록된 과제가 없습니다.")
    st.stop()

a = st.selectbox("과제 선택", assignments, format_func=lambda x: x["title"])
with st.container(border=True):
    st.markdown(f"**논제**\n\n{a['prompt']}")

essay = EssayRepo(db).get_or_create_draft(user["id"], a["id"])
if essay["status"] != "draft":
    st.info("이미 제출한 과제입니다. '제출 내역'에서 피드백을 확인하세요.")
    st.stop()

content = st.text_area("답안", value=essay["content"], height=480,
                       max_chars=get_settings().max_essay_chars)
char_counter(content, a["min_chars"], a["max_chars"])

c1, c2 = st.columns(2)
if c1.button("💾 임시 저장", use_container_width=True):
    EssayRepo(db).save(essay["id"], content)
    st.toast("저장되었습니다.")

if c2.button("🚀 제출하고 AI 첨삭 받기", type="primary", use_container_width=True):
    if not content.strip():
        st.warning("답안을 입력해 주세요.")
    else:
        with st.spinner("AI가 답안을 평가하고 있습니다... (최대 1분)"):
            try:
                fb = feedback_service.submit_and_review(essay["id"], content, a["prompt"])
                st.balloons()
                render_feedback(fb)
            except Exception as e:
                st.error(f"첨삭 중 오류가 발생했습니다: {e}")
