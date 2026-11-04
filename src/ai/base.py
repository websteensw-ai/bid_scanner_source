"""AI 제공자 공통 인터페이스."""
import json
import re
from abc import ABC, abstractmethod

from src.core.models import FeedbackResult


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def _complete(self, system: str, user: str) -> str:
        """모델 원문 응답 텍스트를 반환."""

    def evaluate(self, system: str, user: str) -> FeedbackResult:
        return parse_feedback(self._complete(system, user))


def parse_feedback(text: str) -> FeedbackResult:
    """응답에서 JSON 객체를 추출해 검증. 코드펜스로 감싸진 경우도 처리."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("AI 응답에서 JSON을 찾을 수 없습니다.")
    return FeedbackResult.model_validate(json.loads(match.group(0)))
