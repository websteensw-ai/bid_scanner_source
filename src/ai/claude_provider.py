import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.ai.base import AIProvider

# 거절(refusal) 시 서버가 같은 요청을 대체 모델로 다시 실행하게 한다 (Sonnet 5.5 는 "default" 권장 형태)
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str, max_tokens: int, light_model: str = ""):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=0)   # 재시도는 아래 tenacity 가 맡는다
        self.model = model
        self.light_model = light_model or model
        self.max_tokens = max_tokens
        self.last_stop_reason: str | None = None
        self.last_raw: str = ""
        self._fallbacks_ok = True

    # 일시적 오류(과부하·속도 제한·연결)만 다시 시도한다. 키 오류·잘못된 요청은 바로 실패시킨다.
    @retry(retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError,
                                          anthropic.InternalServerError)),
           stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _complete(self, system: str, user: str, *, max_tokens: int | None = None, effort: str | None = None,
                  light: bool = False) -> str:
        """effort: low/medium/high — 생각의 깊이와 응답 시간. light=True 면 경량 모델(검사기용)."""
        model = self.light_model if light else self.model
        body: dict = {}
        if effort:
            body["output_config"] = {"effort": effort}
        headers = {}
        if self._fallbacks_ok and not light:
            body["fallbacks"] = "default"
            headers["anthropic-beta"] = _FALLBACK_BETA
        try:
            msg = self.client.messages.create(
                model=model, max_tokens=max_tokens or self.max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
                extra_body=body or None, extra_headers=headers or None,
            )
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower() or not self._fallbacks_ok:
                raise
            self._fallbacks_ok = False             # 이 계정·모델에서 대체 모델 기능을 못 쓰면 끄고 다시
            return self._complete(system, user, max_tokens=max_tokens, effort=effort, light=light)
        self.last_stop_reason = msg.stop_reason
        if msg.stop_reason == "refusal":
            self.last_raw = ""
            return ""
        self.last_raw = "".join(b.text for b in msg.content if b.type == "text")
        return self.last_raw
