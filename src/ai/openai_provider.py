from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ai.base import AIProvider


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    def _complete(self, system: str, user: str) -> str:
        res = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return res.choices[0].message.content or ""
