import openai
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.ai.base import AIProvider


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError,
                                          openai.InternalServerError)),
           stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _complete(self, system: str, user: str, *, max_tokens: int | None = None, effort: str | None = None,
                  light: bool = False) -> str:
        res = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return res.choices[0].message.content or ""
