import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ai.base import AIProvider


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    def _complete(self, system: str, user: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
