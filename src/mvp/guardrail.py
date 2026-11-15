"""응답 검사기 (가이드 5-7) — 튜터 발화를 학생에게 보내기 전에 검사한다.

1. 규칙 검사(코드): 물음표 2개 이상, 설정 길이 초과, 예시답안·기준 해석 문장과의 높은 겹침
2. 경량 모델 검사(선택): "이 발화가 학생이 해야 할 해석을 대신 제시하는가?" 예/아니오
위반하면 한 번 다시 생성하고, 그래도 위반이면 안전한 기본 발화로 바꾼다.
"""
import re

from src.mvp.text import max_overlap

PROMPT_VERSION = "checker-0.1"
FALLBACK = "방금 말한 내용을 뒷받침하는 대목을 원문에서 찾아 볼까요?"
OVERLAP_LIMIT = 0.6


def rule_check(utterance: str, references: list[str], max_chars: int = 250) -> dict:
    reasons = []
    q = len(re.findall(r"[?？]", utterance))
    if q >= 2:
        reasons.append(f"질문 {q}개")
    if len(utterance) > max_chars:
        reasons.append(f"길이 {len(utterance)}자")
    if not utterance.strip():
        reasons.append("빈 발화")
    ov = max_overlap(utterance, references) if references else 0.0
    if ov >= OVERLAP_LIMIT:
        reasons.append(f"기준 문장과 겹침 {ov:.2f}")
    return {"ok": not reasons, "reasons": reasons, "overlap": round(ov, 2), "questions": q}


_LIGHT_SYSTEM = ("너는 논술 튜터의 발화를 검사한다. 발화가 학생이 스스로 해야 할 해석이나 완성 문장을 "
                 "대신 제시하면 YES, 아니면 NO 만 답하라.")


def light_check(provider, utterance: str) -> bool | None:
    """경량 모델 검사. 대신 해석을 제시하면 False. 모델이 없으면 None."""
    if provider is None:
        return None
    try:
        out = provider._complete(_LIGHT_SYSTEM, utterance).strip().upper()
    except Exception:
        return None
    return not out.startswith("YES")
