import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.ai.base import AIProvider


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    # 일시적 오류(과부하·속도 제한·연결)만 다시 시도한다. 키 오류·잘못된 요청은 바로 실패시킨다.
    @retry(retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError,
                                          anthropic.InternalServerError)),
           stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _complete(self, system: str, user: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
