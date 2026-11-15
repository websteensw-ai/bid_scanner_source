"""채점 계산 (가이드 8-2) — AI 는 항목별 수준(0~4)과 근거만 내고 점수는 코드가 계산한다.

항목 점수 = 배점 × 수준 ÷ 4 (중간 반올림 없음)
영역 점수 = 항목 점수 합, 총점 = 영역 점수 합 (소수 둘째 자리까지 보존)
본문 > 상한 → E2 = 수준 0 (다른 항목은 전체 답안으로 평가), 초과 글자 수 기록
판정 보류(None)는 0점과 구분하고 총점을 '잠정'으로 표시
"""
from src.mvp.models import EvalItem
from src.mvp.pack import Rubric
from src.mvp.text import anchor_quote


def compute(rubric: Rubric, items: list[EvalItem], chars: int, max_chars: int) -> dict:
    by = {i.code: i for i in items}
    over = max(0, chars - max_chars)
    if over and "E2" in by:
        by["E2"].level = 0
        by["E2"].reason = (by["E2"].reason + f" / 분량 {over}자 초과").strip(" /")
    provisional = False
    areas = {a.code: 0.0 for a in rubric.areas}
    for ri in rubric.items:
        it = by.get(ri.code)
        if it is None or it.level is None:
            provisional = True
            if it is not None:
                it.score = None
            continue
        it.level = max(0, min(4, int(it.level)))
        it.score = ri.points * it.level / 4
        areas[ri.area] += it.score
    areas = {k: round(v, 2) for k, v in areas.items()}
    return {"area_scores": areas, "total": round(sum(areas.values()), 2), "provisional": provisional,
            "over_chars": over}


def fix_evidence(body: str, items: list[EvalItem]) -> list[str]:
    """인용 위치 검증·보정. 찾지 못한 항목 코드를 돌려준다 (호출 측에서 재채점)."""
    missing = []
    for it in items:
        kept = []
        for ev in it.evidence:
            pos = anchor_quote(body, int(ev.get("start", -1)), int(ev.get("end", -1)), ev.get("quote", ""))
            if pos:
                kept.append({"start": pos[0], "end": pos[1], "quote": body[pos[0]:pos[1]]})
            elif ev.get("quote"):
                missing.append(it.code)
        it.evidence = kept
    return missing


def merge_runs(runs: list[list[EvalItem]]) -> tuple[list[EvalItem], list[str]]:
    """2회 독립 채점 결과 합치기. 수준이 2 이상 차이 나는 항목 코드를 돌려준다 (3회째 채점·교사 검토 권장)."""
    first = {i.code: i for i in runs[0]}
    mismatch = []
    for other in runs[1:]:
        for it in other:
            a = first.get(it.code)
            if a and a.level is not None and it.level is not None and abs(a.level - it.level) >= 2:
                mismatch.append(it.code)
    merged = []
    for code, it in first.items():
        levels = [r_it.level for r in runs for r_it in r if r_it.code == code and r_it.level is not None]
        out = it.model_copy(deep=True)
        if levels:
            levels.sort()
            out.level = levels[len(levels) // 2]          # 중앙값 (3회일 때 다수결과 같은 효과)
        out.review_recommended = code in mismatch
        merged.append(out)
    return merged, sorted(set(mismatch))
