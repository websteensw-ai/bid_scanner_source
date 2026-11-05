from streamlit.testing.v1 import AppTest

from src.core.config import Settings
from src.learning.analyzer import DemoAnalyzer


def _login(at: AppTest, login_id: str, pw: str) -> AppTest:
    at.text_input[0].input(login_id)
    at.text_input[1].input(pw)
    at.button[0].click()
    return at.run()


def test_test_login_succeeds_without_supabase():
    at = _login(AppTest.from_file("../app.py").run(), "test", "testpoc")
    assert not at.exception
    assert at.session_state["user"]["is_demo"] is True
    # 로그인 후 학습 홈(오늘의 목표)이 그려져야 함
    assert any("오늘의 목표" in h.proto.body for h in at.get("html"))


def test_wrong_password_is_rejected():
    at = _login(AppTest.from_file("../app.py").run(), "test", "wrong")
    assert "user" not in at.session_state
    assert at.error


def test_test_login_disabled_in_production():
    s = Settings(_env_file=None, app_env="production")
    assert s.test_login_enabled is False


def test_demo_without_key_uses_demo_analyzer(monkeypatch):
    from src.learning import analyzer

    monkeypatch.setattr("src.core.config.get_settings",
                        lambda: Settings(_env_file=None, anthropic_api_key=""))
    assert isinstance(analyzer.get_analyzer(demo=True), DemoAnalyzer)
