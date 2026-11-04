"""환경 설정. .env → 환경변수 → Streamlit secrets 순으로 로드."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # AI
    ai_provider: Literal["claude", "openai"] = "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    ai_max_tokens: int = 4096

    # App
    app_env: Literal["development", "production"] = "development"
    max_essay_chars: int = 5000

    # 테스트 로그인 (Supabase 없이 데모 데이터로 동작). 운영 환경에서는 자동 비활성화
    enable_test_login: bool = True
    test_login_id: str = "test"
    test_login_password: str = "testpoc"

    @property
    def test_login_enabled(self) -> bool:
        return self.enable_test_login and self.app_env != "production"


def _load_streamlit_secrets() -> dict:
    try:
        import streamlit as st

        return {k.lower(): v for k, v in st.secrets.items() if not isinstance(v, dict)}
    except Exception:
        return {}


@lru_cache
def get_settings() -> Settings:
    secrets = _load_streamlit_secrets()
    return Settings(**secrets) if secrets else Settings()
