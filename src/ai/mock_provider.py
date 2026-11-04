"""API 키 없이 화면을 확인하기 위한 데모용 평가기.

실제 AI가 아니라 글자 수·문단 수 같은 간단한 지표로 점수를 만들고
정해진 문구를 돌려줍니다. 테스트 로그인 + API 키 미설정일 때만 사용됩니다.
"""
import re

from src.ai.base import AIProvider
from src.ai.prompts import RUBRIC
from src.core.models import CriterionScore, FeedbackResult, InlineCorrection

_ESSAY_RE = re.compile(r"<학생_답안>\n(.*)\n</학생_답안>", re.DOTALL)

_COMMON_FIXES = [
    ("되요", "돼요", "'되어요'의 준말은 '돼요'입니다."),
    ("안되", "안 되", "부정의 '안'은 뒤 말과 띄어 씁니다."),
    ("할수", "할 수", "의존 명사 '수'는 띄어 씁니다."),
    ("것 같다", "것이다", "논술에서는 단정적 표현이 주장을 더 분명하게 합니다."),
]


class MockProvider(AIProvider):
    name = "demo"
    model = "mock-evaluator"

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - evaluate 직접 구현
        raise NotImplementedError

    def evaluate(self, system: str, user: str) -> FeedbackResult:
        m = _ESSAY_RE.search(user)
        essay = m.group(1) if m else user
        chars = len(re.sub(r"\s", "", essay))
        paragraphs = len([p for p in essay.split("\n") if p.strip()])

        base = min(9, 4 + chars // 250)
        bonus = 1 if paragraphs >= 3 else 0
        # '구성'은 문단 수 보너스, '창의성'은 한 단계 낮게
        scores = [base] * len(RUBRIC)
        scores[2] = min(10, base + bonus)
        scores[4] = base - 1
        criteria = [
            CriterionScore(criterion=name, score=max(0, s),
                           comment=f"(데모) {desc}에 대한 예시 코멘트입니다.")
            for (name, desc), s in zip(RUBRIC, scores, strict=True)
        ]
        corrections = [InlineCorrection(original=o, suggestion=n, reason=r)
                       for o, n, r in _COMMON_FIXES if o in essay]

        return FeedbackResult(
            total_score=round(sum(c.score for c in criteria) / (10 * len(criteria)) * 100),
            criteria=criteria,
            strengths=["자신의 입장을 글의 앞부분에서 밝혔습니다.",
                       f"공백 제외 {chars:,}자, {paragraphs}개 문단으로 구성했습니다."],
            improvements=["주장을 뒷받침하는 구체적 사례나 통계를 보강해 보세요.",
                          "예상되는 반론을 소개하고 재반박하면 논증이 단단해집니다."],
            corrections=corrections,
            summary="⚠️ 데모 평가입니다. 실제 AI 첨삭을 받으려면 .env 에 "
                    "ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 를 설정하세요.",
        )
