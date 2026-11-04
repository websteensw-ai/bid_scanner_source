import streamlit as st

from src.db.factory import get_repos
from src.services import auth_service
from src.ui.components import _e, card, chip, empty_state, hero, html, stat_grid

user = auth_service.require_login()
repos = get_repos()
name = user.get("full_name") or user["email"]

hero(f"{name} 님, 오늘도 한 편 써볼까요?",
     "꾸준히 쓰고 피드백을 반영하는 것이 논술 실력을 올리는 가장 빠른 길이에요.",
     eyebrow="논술랩 대시보드")

essays = repos.essays.list_by_student(user["id"])
scores = [fb["total_score"] for e in essays for fb in (e.get("feedbacks") or [])[:1]]
assignments = repos.assignments.list_open()
by_assignment = {e["assignment_id"]: e for e in essays}

stat_grid([
    ("📚", "진행 중인 과제", f"{len(assignments)}", "개"),
    ("📮", "제출한 논술", f"{sum(e['status'] != 'draft' for e in essays)}", "편"),
    ("📈", "평균 점수", f"{sum(scores) / len(scores):.0f}" if scores else "–", "점"),
    ("🏅", "최근 점수", f"{scores[0]}" if scores else "–", "점"),
])

html('<h3 style="margin:1.6rem 0 .8rem;font-size:1.2rem">과제 목록</h3>')

if not assignments:
    empty_state("🗂️", "아직 등록된 과제가 없어요", "선생님이 과제를 출제하면 여기에 표시돼요.")

cols = st.columns(2, gap="medium")
for i, a in enumerate(assignments):
    e = by_assignment.get(a["id"])
    status = e["status"] if e else "draft"
    with cols[i % 2], card(f"a_{i}"):
        html(f'<div class="nx-card-meta">{chip(status)}'
             f'<span>권장 {a["min_chars"]:,}~{a["max_chars"]:,}자</span></div>'
             f'<div class="nx-card-title" style="margin-top:.7rem">{_e(a["title"])}</div>'
             f'<p style="color:var(--text-muted);font-size:.92rem;line-height:1.65;margin:0">'
             f'{_e(a["prompt"][:90])}{"…" if len(a["prompt"]) > 90 else ""}</p>')
        if user["role"] in ("student", "admin"):
            label = {"draft": "작성하기", "submitted": "결과 보기", "reviewed": "첨삭 보기"}[status]
            if st.button(label, key=f"go_{i}", use_container_width=True,
                         type="primary" if status == "draft" else "secondary"):
                st.session_state["selected_assignment"] = a["id"]
                st.switch_page("views/write.py" if status == "draft" else "views/history.py")
