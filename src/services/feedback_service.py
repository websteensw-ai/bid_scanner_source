"""논술 제출 → AI 평가 → 피드백 저장 오케스트레이션."""
from src.ai.factory import get_provider
from src.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from src.core.models import FeedbackResult
from src.db.client import get_supabase
from src.db.repositories import EssayRepo, FeedbackRepo


def submit_and_review(essay_id: str, content: str, assignment_prompt: str) -> FeedbackResult:
    db = get_supabase()
    EssayRepo(db).submit(essay_id, content)

    provider = get_provider()
    result = provider.evaluate(SYSTEM_PROMPT, build_user_prompt(assignment_prompt, content))

    FeedbackRepo(db).create(essay_id, result, provider.name, provider.model)
    return result
