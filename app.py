"""논술 프로그램 진입점 (홈 / 로그인).

실행: streamlit run app.py
"""
import streamlit as st

from src.services import auth_service

st.set_page_config(page_title="AI 논술 첨삭", page_icon="📝", layout="wide")

st.title("📝 AI 논술 첨삭 프로그램")
user = auth_service.current_user()

if user:
    st.success(f"{user.get('full_name') or user['email']} 님 ({user['role']}) 환영합니다.")
    st.markdown(
        "왼쪽 메뉴에서 이동하세요.\n"
        "- **논술 작성**: 과제를 선택해 글을 쓰고 제출하면 AI 첨삭을 받습니다.\n"
        "- **제출 내역**: 지난 제출물과 피드백을 확인합니다.\n"
        "- **교사 대시보드**: 과제 출제 및 학생 제출물 관리 (교사 전용)"
    )
    if st.button("로그아웃"):
        auth_service.sign_out()
        st.rerun()
else:
    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
    with login_tab, st.form("login"):
        email = st.text_input("이메일")
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인", type="primary"):
            try:
                auth_service.sign_in(email, pw)
                st.rerun()
            except Exception as e:
                st.error(f"로그인 실패: {e}")
    with signup_tab, st.form("signup"):
        name = st.text_input("이름")
        email = st.text_input("이메일", key="su_email")
        pw = st.text_input("비밀번호 (6자 이상)", type="password", key="su_pw")
        if st.form_submit_button("가입하기"):
            try:
                auth_service.sign_up(email, pw, name)
                st.success("가입 완료! 이메일 인증 후 로그인해 주세요.")
            except Exception as e:
                st.error(f"가입 실패: {e}")
