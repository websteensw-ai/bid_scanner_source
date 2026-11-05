"""AI 제공자 공통 인터페이스. 답변 분석 프롬프트는 src/learning/analyzer.py 에 있다."""
from abc import ABC, abstractmethod


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def _complete(self, system: str, user: str) -> str:
        """모델 원문 응답 텍스트를 반환."""
