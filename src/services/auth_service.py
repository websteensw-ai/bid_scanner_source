"""인증. 로그인 상태는 st.session_state["user"] 에 보관.

- 일반 로그인: Supabase Auth (이메일/비밀번호)
- 테스트 로그인: 설정된 아이디/비밀번호(기본 test / testpoc)와 일치하면
  Supabase 없이 데모 저장소로 동작. APP_ENV=production 에서는 비활성화.
"""
import hmac

import streamlit as st

from src.core.config import get_settings
from src.db.demo_store import DEMO_USER_ID


def _is_test_credentials(login_id: str, password: str) -> bool:
    s = get_settings()
    if not s.test_login_enabled:
        return False
    return (hmac.compare_digest(login_id.strip(), s.test_login_id)
            and hmac.compare_digest(password, s.test_login_password))


def sign_in(login_id: str, password: str) -> None:
    if _is_test_credentials(login_id, password):
        st.session_state["user"] = {
            "id": DEMO_USER_ID,
            "email": login_id.strip(),
            "full_name": "테스트 사용자",
            "role": "admin",          # 학생·교사 화면을 모두 확인할 수 있도록
            "is_demo": True,
        }
        return

    from src.db.client import get_supabase

    db = get_supabase()
    res = db.auth.sign_in_with_password({"email": login_id, "password": password})
    profile = db.table("profiles").select("*").eq("id", res.user.id).single().execute().data
    st.session_state["user"] = profile


def sign_up(email: str, password: str, full_name: str) -> None:
    from src.db.client import get_supabase

    get_supabase().auth.sign_up({
        "email": email,
        "password": password,
        "options": {"data": {"full_name": full_name}},  # 트리거가 profiles 행 생성
    })


def sign_out() -> None:
    user = st.session_state.pop("user", None)
    st.session_state.pop("demo_store", None)
    if user and not user.get("is_demo"):
        from src.db.client import get_supabase

        get_supabase().auth.sign_out()


def current_user() -> dict | None:
    return st.session_state.get("user")


def require_login(*roles: str) -> dict:
    """페이지 상단에서 호출. 로그인/권한이 없으면 렌더링 중단. admin 은 모든 페이지 접근 가능."""
    user = current_user()
    if not user:
        st.warning("먼저 홈 화면에서 로그인해 주세요.")
        st.stop()
    if roles and user["role"] not in roles and user["role"] != "admin":
        st.error("이 페이지에 접근할 권한이 없습니다.")
        st.stop()
    if user.get("is_demo"):
        st.sidebar.info("🧪 테스트 계정으로 접속 중\n\n"
                        "데이터는 이 브라우저 세션에만 임시 저장됩니다.")
    return user
