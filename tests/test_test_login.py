from streamlit.testing.v1 import AppTest

from src.ai.factory import get_provider
from src.ai.mock_provider import MockProvider
from src.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from src.core.config import Settings


def _login(at: AppTest, login_id: str, pw: str) -> AppTest:
    at.text_input[0].input(login_id)
    at.text_input[1].input(pw)
    at.button[0].click()
    return at.run()


def test_test_login_succeeds_without_supabase():
    at = _login(AppTest.from_file("../app.py").run(), "test", "testpoc")
    assert not at.exception
    assert at.session_state["user"]["is_demo"] is True
    # 로그인 후 홈 대시보드가 그려져야 함
    assert any("테스트 사용자" in h.proto.body for h in at.get("html"))


def test_wrong_password_is_rejected():
    at = _login(AppTest.from_file("../app.py").run(), "test", "wrong")
    assert "user" not in at.session_state
    assert at.error


def test_test_login_disabled_in_production():
    s = Settings(_env_file=None, app_env="production")
    assert s.test_login_enabled is False


def test_demo_without_key_uses_mock_provider():
    s = Settings(_env_file=None, anthropic_api_key="")
    assert isinstance(get_provider(s, demo=True), MockProvider)


def test_mock_provider_returns_valid_feedback():
    essay = "첫 문단입니다.\n\n둘째 문단에서 할수 있다.\n\n셋째 문단." * 20
    fb = MockProvider().evaluate(SYSTEM_PROMPT, build_user_prompt("논제", essay))
    assert 0 <= fb.total_score <= 100
    assert any(c.original == "할수" for c in fb.corrections)
