import streamlit as st

from src.ai.prompts import RUBRIC
from src.core.config import get_settings
from src.db.factory import get_repos
from src.services import auth_service, feedback_service
from src.ui.components import (
    _e,
    card,
    char_progress,
    chip,
    empty_state,
    html,
    page_header,
    render_feedback,
    writing_tips,
)

user = auth_service.require_login("student")
repos = get_repos()

page_header("논술 작성", "논제를 꼼꼼히 읽고, 자신의 입장을 논리적으로 펼쳐 보세요.",
            eyebrow="✍️ Writing")

assignments = repos.assignments.list_open()
if not assignments:
    empty_state("🗂️", "아직 등록된 과제가 없어요", "선생님이 과제를 출제하면 여기에서 작성할 수 있어요.")
    st.stop()

ids = [a["id"] for a in assignments]
preselected = st.session_state.pop("selected_assignment", None)
a = st.selectbox("과제 선택", assignments, format_func=lambda x: x["title"],
                 index=ids.index(preselected) if preselected in ids else 0)
essay = repos.essays.get_or_create_draft(user["id"], a["id"])

with card("prompt"):
    html(f'<div class="nx-card-meta" style="margin-bottom:.6rem">{chip(essay["status"])}'
         f'<span>권장 분량 {a["min_chars"]:,}~{a["max_chars"]:,}자</span></div>'
         f'<div class="nx-label">논제</div><p class="nx-prompt">{_e(a["prompt"])}</p>')

if essay["status"] != "draft":
    st.info("이미 제출한 과제예요. 첨삭 결과는 **첨삭 기록**에서 확인할 수 있어요.", icon="📬")
    if st.button("첨삭 기록으로 이동", type="primary"):
        st.switch_page("views/history.py")
    st.stop()

main, side = st.columns([2.3, 1], gap="large")

with main:
    content = st.text_area("답안", value=essay["content"], height=520, key="editor",
                           max_chars=get_settings().max_essay_chars,
                           label_visibility="collapsed",
                           placeholder="여기에 답안을 작성하세요.\n\n"
                                       "서론 – 논제에 대한 나의 입장\n"
                                       "본론 – 근거와 사례, 예상 반론과 재반박\n"
                                       "결론 – 핵심 요약과 의의")
    char_progress(content, a["min_chars"], a["max_chars"])

    b1, b2 = st.columns([1, 1.6], gap="small")
    if b1.button("임시 저장", icon=":material/save:", use_container_width=True):
        repos.essays.save(essay["id"], content)
        st.toast("임시 저장했어요.", icon="💾")
    submit = b2.button("제출하고 AI 첨삭 받기", icon=":material/auto_awesome:", type="primary",
                       use_container_width=True)

with side:
    with card("rubric"):
        html('<div class="nx-label">평가 기준</div>' + "".join(
            f'<div class="nx-tip"><span class="n">{i}</span><span><b>{_e(n)}</b><br>'
            f'<span style="color:var(--text-muted);font-size:.86rem">{_e(d)}</span></span></div>'
            for i, (n, d) in enumerate(RUBRIC, 1)))
    with card("tips"):
        html('<div class="nx-label">작성 팁</div>')
        writing_tips()

if submit:
    if not content.strip():
        st.warning("답안을 입력해 주세요.")
    else:
        with st.spinner("AI 선생님이 답안을 꼼꼼히 읽고 있어요… (최대 1분)"):
            try:
                fb = feedback_service.submit_and_review(essay["id"], content, a["prompt"])
            except Exception as e:
                st.error(f"첨삭 중 문제가 생겼어요: {e}")
                st.stop()
        st.balloons()
        html('<h3 style="margin:2rem 0 1rem;font-size:1.3rem">📋 첨삭 결과</h3>')
        render_feedback(fb, key="new")
