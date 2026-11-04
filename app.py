"""논술랩 진입점: 테마 적용 + 로그인 상태/역할에 따른 메뉴 구성.

실행: streamlit run app.py
"""
import streamlit as st

from src.services import auth_service
from src.ui.components import user_badge
from src.ui.theme import apply_theme

st.set_page_config(page_title="논술랩 · AI 논술 첨삭", page_icon="assets/icon.svg",
                   layout="wide", initial_sidebar_state="auto")
apply_theme()

user = auth_service.current_user()

if not user:
    nav = st.navigation([st.Page("views/login.py", title="로그인", icon=":material/login:")],
                        position="hidden")
else:
    is_staff = user["role"] in ("teacher", "admin")
    is_student = user["role"] in ("student", "admin")
    pages: dict[str, list] = {"": [st.Page("views/home.py", title="홈", icon=":material/home:",
                                           default=True)]}
    if is_student:
        pages["학습"] = [
            st.Page("views/write.py", title="논술 작성", icon=":material/edit_note:"),
            st.Page("views/history.py", title="첨삭 기록", icon=":material/history_edu:"),
        ]
    if is_staff:
        pages["관리"] = [
            st.Page("views/teacher.py", title="교사 대시보드", icon=":material/dashboard:"),
        ]
    nav = st.navigation(pages)

    st.logo("assets/logo.svg", icon_image="assets/icon.svg", size="large")
    with st.sidebar:
        user_badge(user)
        if st.button("로그아웃", icon=":material/logout:", use_container_width=True):
            auth_service.sign_out()
            st.rerun()

nav.run()
