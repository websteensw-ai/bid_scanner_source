"""논술랩 진입점: 테마 적용 + 로그인 상태/역할에 따른 메뉴 구성.

실행: streamlit run app.py
"""
import streamlit as st

from src.services import auth_service
from src.ui.components import user_badge
from src.ui.theme import apply_theme

st.set_page_config(page_title="논술랩 · 기초 다지기", page_icon="assets/icon.svg",
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
        pages["기초 다지기"] = [
            st.Page("views/lesson.py", title="학습하기", icon=":material/edit_note:"),
            st.Page("views/result.py", title="진단 결과", icon=":material/explore:"),
            st.Page("views/review.py", title="선택 복습", icon=":material/menu_book:"),
        ]
    if is_staff:
        pages["교사·운영자"] = [
            st.Page("views/records.py", title="학습 기록", icon=":material/fact_check:"),
            st.Page("views/content_admin.py", title="자료 관리", icon=":material/inventory_2:"),
            st.Page("views/quality.py", title="AI 품질", icon=":material/science:"),
        ]
        if not is_student:
            pages[""] = [st.Page("views/records.py", title="학습 기록", icon=":material/fact_check:",
                                 default=True)]
            pages["교사·운영자"] = pages["교사·운영자"][1:]
    nav = st.navigation(pages)

    st.logo("assets/logo.svg", icon_image="assets/icon.svg", size="large")
    with st.sidebar:
        user_badge(user)
        if st.button("로그아웃", icon=":material/logout:", width="stretch"):
            auth_service.sign_out()
            st.rerun()

nav.run()
