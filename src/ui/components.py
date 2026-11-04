"""재사용 UI 컴포넌트. 스타일은 src/ui/theme.py 의 .nx-* 클래스를 사용합니다.

학생 답안·AI 응답 등 외부 텍스트는 반드시 _e() 로 이스케이프한 뒤 HTML 에 넣습니다.
"""
from html import escape

import streamlit as st

from src.core.models import FeedbackResult

STATUS_LABEL = {"draft": "작성 중", "submitted": "평가 대기", "reviewed": "첨삭 완료"}
ROLE_LABEL = {"student": "학생", "teacher": "교사", "admin": "관리자"}


def _e(text: object) -> str:
    return escape(str(text or ""))


def html(markup: str) -> None:
    st.html(markup)


# ---------- 레이아웃 ----------
def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    eb = f'<div class="nx-eyebrow">{_e(eyebrow)}</div>' if eyebrow else ""
    sub = f'<p class="nx-subtitle">{_e(subtitle)}</p>' if subtitle else ""
    html(f'<div class="nx-header">{eb}<h1 class="nx-title">{_e(title)}</h1>{sub}</div>')


def hero(title: str, body: str, eyebrow: str = "") -> None:
    eb = f'<div class="nx-eyebrow">{_e(eyebrow)}</div>' if eyebrow else ""
    html(f'<div class="nx-hero">{eb}<h2>{_e(title)}</h2><p>{_e(body)}</p></div>')


def card(key: str):
    """흰 배경·둥근 모서리·그림자 카드 컨테이너. key 는 화면 내에서 고유해야 합니다."""
    return st.container(key=f"card_{key}")


def _stat(icon: str, label: str, value: str, unit: str = "") -> str:
    unit_html = f" <small>{_e(unit)}</small>" if unit else ""
    return (f'<div class="nx-stat"><div class="icon">{_e(icon)}</div>'
            f'<div class="label">{_e(label)}</div>'
            f'<div class="value">{_e(value)}{unit_html}</div></div>')


def stat_grid(items: list[tuple[str, str, str, str]]) -> None:
    """(아이콘, 라벨, 값, 단위) 목록을 반응형 그리드로. 데스크톱 한 줄, 모바일 2열."""
    html(f'<div class="nx-stats" style="--n:{len(items)}">'
         + "".join(_stat(*it) for it in items) + "</div>")


def chip(status: str) -> str:
    return f'<span class="nx-chip {_e(status)}">{_e(STATUS_LABEL.get(status, status))}</span>'


def empty_state(icon: str, title: str, body: str) -> None:
    html(f'<div class="nx-empty"><div class="ico">{_e(icon)}</div>'
         f'<h4>{_e(title)}</h4><p>{_e(body)}</p></div>')


def user_badge(user: dict) -> None:
    name = user.get("full_name") or user.get("email") or "사용자"
    role = ROLE_LABEL.get(user.get("role", ""), user.get("role", ""))
    demo = ' · <span style="color:var(--primary)">테스트</span>' if user.get("is_demo") else ""
    html(f'<div class="nx-user"><div class="nx-avatar">{_e(name[:1])}</div>'
         f'<div><div class="nm">{_e(name)}</div><div class="rl">{_e(role)}{demo}</div></div></div>')


# ---------- 작성 화면 ----------
def count_chars(text: str) -> int:
    return len(text.replace(" ", "").replace("\n", ""))


def char_progress(text: str, min_chars: int, max_chars: int) -> bool:
    """권장 분량 구간을 표시하는 진행바. 권장 범위 안이면 True."""
    n = count_chars(text)
    scale = max_chars * 1.15
    pct = min(100, n / scale * 100)
    ok = min_chars <= n <= max_chars
    color = "var(--success)" if ok else ("var(--danger)" if n > max_chars else "var(--primary)")
    state = "권장 분량 충족" if ok else ("분량 초과" if n > max_chars else
                                     f"{min_chars - n:,}자 더 쓰면 권장 분량")
    z0, z1 = min_chars / scale * 100, max_chars / scale * 100
    html(f'<div class="nx-progress"><div class="row"><span><b>{n:,}</b>자 · 공백 제외</span>'
         f'<span>{state} ({min_chars:,}~{max_chars:,}자)</span></div>'
         f'<div class="track"><div class="zone" style="left:{z0:.1f}%;width:{z1 - z0:.1f}%"></div>'
         f'<div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div></div>')
    return ok


def writing_tips() -> None:
    tips = [
        "첫 문단에서 <b>자신의 입장</b>을 한 문장으로 분명히 밝히세요.",
        "근거마다 <b>사례·통계·이론</b> 중 하나를 붙이면 설득력이 높아집니다.",
        "<b>예상 반론</b>을 소개하고 재반박하면 논증이 단단해집니다.",
        "결론에서는 새 주장보다 <b>핵심 요약과 의의</b>를 정리하세요.",
    ]
    html("".join(f'<div class="nx-tip"><span class="n">{i}</span><span>{t}</span></div>'
                 for i, t in enumerate(tips, 1)))


# ---------- 피드백 ----------
def _grade(score: int) -> tuple[str, str]:
    if score >= 90:
        return "탁월해요", "var(--success)"
    if score >= 75:
        return "잘 썼어요", "var(--primary)"
    if score >= 60:
        return "조금만 더 다듬어 봐요", "var(--warning)"
    return "기본기를 함께 다져봐요", "var(--danger)"


def render_feedback(fb: FeedbackResult, key: str = "fb") -> None:
    grade, color = _grade(fb.total_score)

    with card(f"{key}_score"):
        html(f'<div class="nx-score">'
             f'<div class="nx-ring" style="--p:{fb.total_score};--c:{color}">'
             f'<div><div><b>{fb.total_score}</b><br><span>/ 100점</span></div></div></div>'
             f'<div class="summary"><div class="nx-label">AI 종합 평가</div>'
             f'<div class="grade">{grade}</div><p>{_e(fb.summary)}</p></div></div>')

    left, right = st.columns([1, 1], gap="medium")
    with left, card(f"{key}_crit"):
        html('<div class="nx-label">항목별 점수</div>' + "".join(
            f'<div class="nx-crit"><div class="head"><span class="name">{_e(c.criterion)}</span>'
            f'<span class="pt">{c.score}<small> / 10</small></span></div>'
            f'<div class="bar"><div style="width:{c.score * 10}%"></div></div>'
            f'<div class="cmt">{_e(c.comment)}</div></div>'
            for c in fb.criteria))
    with right:
        with card(f"{key}_good"):
            html('<div class="nx-label">잘한 점</div><ul class="nx-list good">' + "".join(
                f'<li data-i="✓">{_e(s)}</li>' for s in fb.strengths) + "</ul>")
        with card(f"{key}_todo"):
            html('<div class="nx-label">보완할 점</div><ul class="nx-list todo">' + "".join(
                f'<li data-i="{i}">{_e(s)}</li>' for i, s in enumerate(fb.improvements, 1))
                 + "</ul>")

    if fb.corrections:
        with card(f"{key}_fix"):
            html('<div class="nx-label">문장 첨삭</div>' + "".join(
                f'<div class="nx-fix"><span class="before">{_e(c.original)}</span>'
                f' &nbsp;→&nbsp; <span class="after">{_e(c.suggestion)}</span>'
                f'<div class="why">{_e(c.reason)}</div></div>'
                for c in fb.corrections))
