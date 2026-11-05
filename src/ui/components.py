"""재사용 UI 컴포넌트. 스타일은 src/ui/theme.py 의 .nx-* 클래스를 사용합니다.

학생 답안·AI 응답 등 외부 텍스트는 반드시 _e() 로 이스케이프한 뒤 HTML 에 넣습니다.
"""
from html import escape

import streamlit as st

STATUS_LABEL = {"todo": "시작 전", "active": "진행 중", "paused": "잠시 멈춤", "done": "완료",
                "draft": "작성 중", "submitted": "평가 대기", "reviewed": "첨삭 완료"}
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


# ---------- 학습 화면 ----------
def passage(ex) -> None:
    """중립 기호와 승인된 본문만 표시 (P-018). 제목·저자·출처는 절대 출력하지 않는다."""
    paras = "".join(
        (f'<span class="nx-mark">{_e(ex.marks[i])}</span>' if i in ex.marks else "")
        + f"<p>{_e(t)}</p>" for i, t in enumerate(ex.paragraphs))
    html(f'<div class="nx-passage"><div class="lbl">{_e(ex.label)}</div>{paras}</div>')


def interpretation(text: str) -> None:
    """학습용 해석 문장은 원문과 구별해 표시 (L3-044)."""
    html(f'<div class="nx-interp"><div class="tag">학습용 해석 문장 · 원문 아님</div>'
         f'<p>{_e(text)}</p></div>')


def task_box(title: str, prompt: str, idx: int, total: int) -> None:
    html(f'<div class="nx-task"><div class="nx-label">활동 {idx} / {total}</div>'
         f'<div class="nx-card-title">{_e(title)}</div><p class="nx-prompt">{_e(prompt)}</p></div>')


_KIND_TAG = {"direction": "생각해 볼 질문", "explanation": "설명", "demo": "시범 (다른 글)",
             "guide": "과제 안내", "vocab": "어휘 뜻", "structure": "비교표", "confirm": "확인 질문",
             "done": "해냈어요", "ack": "자기검토", "prompt": "", "help": ""}


def chat(messages) -> None:
    out = []
    for m in messages:
        if m.role == "student":
            out.append(f'<div class="nx-msg me"><div>{_e(m.text)}</div></div>')
        else:
            tag = _KIND_TAG.get(m.kind, "")
            tag_html = f'<div class="tag">{_e(tag)}</div>' if tag else ""
            out.append(f'<div class="nx-msg tutor {_e(m.kind)}">{tag_html}<div>{_e(m.text)}</div></div>')
    if out:
        html('<div class="nx-chat">' + "".join(out) + "</div>")


def step_dots(states: list[str]) -> None:
    """활동 진행 표시. states: done / skipped / current / todo"""
    html('<div class="nx-dots">' + "".join(f'<span class="{s}"></span>' for s in states) + "</div>")


def char_meter(n: int, limit: int) -> None:
    over = n > limit
    pct = min(100, n / limit * 100)
    color = "var(--danger)" if over else "var(--primary)"
    msg = f"{n - limit}자 넘었어요. 제출 전에 직접 줄여 보세요." if over else f"{limit - n}자 남았어요."
    html(f'<div class="nx-progress"><div class="row"><span><b>{n}</b> / {limit}자 · 공백 포함</span>'
         f'<span>{msg}</span></div><div class="track">'
         f'<div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div></div>')


def bullet_list(items: list[str], kind: str = "good") -> None:
    mark = "✓" if kind == "good" else "•"
    html(f'<ul class="nx-list {kind}">' + "".join(f'<li data-i="{mark}">{_e(i)}</li>' for i in items)
         + "</ul>")
