from src.ai.base import AIProvider
from src.core.config import Settings, get_settings


def get_provider(settings: Settings | None = None, demo: bool = False) -> AIProvider:
    """demo=True(테스트 로그인)이고 선택한 AI의 키가 없으면 데모 평가기를 사용."""
    s = settings or get_settings()
    key = s.anthropic_api_key if s.ai_provider == "claude" else s.openai_api_key
    if demo and not key:
        from src.ai.mock_provider import MockProvider

        return MockProvider()

    if s.ai_provider == "claude":
        from src.ai.claude_provider import ClaudeProvider

        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")
        return ClaudeProvider(s.anthropic_api_key, s.anthropic_model, s.ai_max_tokens)

    from src.ai.openai_provider import OpenAIProvider

    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 가 설정되지 않았습니다.")
    return OpenAIProvider(s.openai_api_key, s.openai_model, s.ai_max_tokens)
