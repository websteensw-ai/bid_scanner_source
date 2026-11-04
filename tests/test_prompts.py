import json

import pytest

from src.ai.base import parse_feedback
from src.ai.prompts import RUBRIC, SYSTEM_PROMPT, build_user_prompt

SAMPLE = {
    "total_score": 78,
    "criteria": [{"criterion": n, "score": 8, "comment": "좋음"} for n, _ in RUBRIC],
    "strengths": ["주장이 명확함"],
    "improvements": ["반론 검토 부족"],
    "corrections": [{"original": "되요", "suggestion": "돼요", "reason": "맞춤법"}],
    "summary": "전반적으로 우수합니다.",
}


def test_system_prompt_contains_rubric():
    for name, _ in RUBRIC:
        assert name in SYSTEM_PROMPT


def test_user_prompt_wraps_inputs():
    p = build_user_prompt("논제A", "답안B")
    assert "<논제>\n논제A" in p and "<학생_답안>\n답안B" in p


def test_parse_feedback_handles_code_fence():
    text = f"```json\n{json.dumps(SAMPLE, ensure_ascii=False)}\n```"
    fb = parse_feedback(text)
    assert fb.total_score == 78 and len(fb.criteria) == len(RUBRIC)


def test_parse_feedback_rejects_garbage():
    with pytest.raises(ValueError):
        parse_feedback("no json here")
