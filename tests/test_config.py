from src.ai.factory import get_provider
from src.core.config import Settings


def test_missing_key_raises():
    import pytest

    with pytest.raises(RuntimeError):
        get_provider(Settings(_env_file=None, ai_provider="claude", anthropic_api_key=""))
