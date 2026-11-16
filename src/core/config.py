"""환경 설정. 환경변수(Vercel 프로젝트 설정) 또는 로컬 .env 에서 읽는다."""
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
    anthropic_light_model: str = "claude-haiku-5-5"   # 응답 검사기 (가이드 5-7 '경량 모델 검사')
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    ai_max_tokens: int = 4096
    eval_judge_model: str = ""          # Ragas judge 모델 (비우면 claude-opus-5-5 / gpt-4o)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
