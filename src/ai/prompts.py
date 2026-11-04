"""논술 평가 프롬프트. 평가 기준(루브릭)은 여기서 한 곳에서 관리합니다."""
import json

from src.core.models import FeedbackResult

RUBRIC = [
    ("논제 이해", "논제의 요구를 정확히 파악하고 그에 맞게 답했는가"),
    ("논증력", "주장이 명확하고 근거가 타당하며 충분한가"),
    ("구성", "서론-본론-결론의 흐름과 문단 간 연결이 자연스러운가"),
    ("표현", "어휘·문장이 정확하고 간결하며 맞춤법을 지켰는가"),
    ("창의성", "독창적 관점이나 깊이 있는 사고가 드러나는가"),
]

SYSTEM_PROMPT = f"""당신은 대한민국 고등학생 논술을 지도하는 경험 많은 첨삭 교사입니다.
학생의 글을 아래 루브릭으로 평가하고, 성장을 돕는 구체적이고 따뜻한 피드백을 제공합니다.

[루브릭] (각 항목 0~10점)
{chr(10).join(f"- {name}: {desc}" for name, desc in RUBRIC)}

[규칙]
- total_score 는 항목 점수 합계를 100점 만점으로 환산한 값입니다.
- corrections 의 original 은 학생 원문에서 그대로 인용합니다 (최대 5개).
- 반드시 아래 JSON 스키마에 맞는 JSON 객체 하나만 출력합니다. 다른 텍스트는 쓰지 않습니다.

[JSON 스키마]
{json.dumps(FeedbackResult.model_json_schema(), ensure_ascii=False)}
"""


def build_user_prompt(assignment_prompt: str, essay: str) -> str:
    return f"""<논제>
{assignment_prompt}
</논제>

<학생_답안>
{essay}
</학생_답안>

위 답안을 평가해 JSON으로 응답하세요."""
