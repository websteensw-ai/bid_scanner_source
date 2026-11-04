"""논술 제출 → AI 평가 → 피드백 저장 오케스트레이션."""
from src.ai.factory import get_provider
from src.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from src.core.models import FeedbackResult
from src.db.factory import get_repos, is_demo_session


def submit_and_review(essay_id: str, content: str, assignment_prompt: str) -> FeedbackResult:
    repos = get_repos()
    repos.essays.submit(essay_id, content)

    provider = get_provider(demo=is_demo_session())
    result = provider.evaluate(SYSTEM_PROMPT, build_user_prompt(assignment_prompt, content))

    repos.feedbacks.create(essay_id, result, provider.name, provider.model)
    return result
