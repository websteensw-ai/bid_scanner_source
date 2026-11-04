"""Supabase Auth 래퍼. 로그인 상태는 st.session_state 에 보관."""
import streamlit as st

from src.db.client import get_supabase


def sign_in(email: str, password: str) -> None:
    db = get_supabase()
    res = db.auth.sign_in_with_password({"email": email, "password": password})
    profile = db.table("profiles").select("*").eq("id", res.user.id).single().execute().data
    st.session_state["user"] = profile


def sign_up(email: str, password: str, full_name: str) -> None:
    get_supabase().auth.sign_up({
        "email": email,
        "password": password,
        "options": {"data": {"full_name": full_name}},  # 트리거가 profiles 행 생성
    })


def sign_out() -> None:
    get_supabase().auth.sign_out()
    st.session_state.pop("user", None)


def current_user() -> dict | None:
    return st.session_state.get("user")


def require_login(*roles: str) -> dict:
    """페이지 상단에서 호출. 로그인/권한이 없으면 페이지 렌더링을 중단."""
    user = current_user()
    if not user:
        st.warning("먼저 홈 화면에서 로그인해 주세요.")
        st.stop()
    if roles and user["role"] not in roles:
        st.error("이 페이지에 접근할 권한이 없습니다.")
        st.stop()
    return user
