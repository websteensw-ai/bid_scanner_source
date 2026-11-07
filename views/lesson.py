"""수업 화면. 학생에게는 오늘의 목표, 현재 과제, 필요한 도움, 할 수 있게 된 것, 다음 활동만 보인다 (Z-044).
내부 판단 기준·수준·상태 코드는 표시하지 않는다."""
import streamlit as st

from src.learning.content import count_chars
from src.learning.engine import LearningError, answered
from src.services import auth_service
from src.services.learning_service import my_engine, save
from src.ui.components import (
    _e,
    bullet_list,
    card,
    char_meter,
    chat,
    html,
    interpretation,
    page_header,
    passage,
    step_dots,
    task_box,
)

user = auth_service.require_login("student")
eng = my_engine()
key = st.session_state.get("lesson_key")
if not key:
    first = next((t for t in eng.pack().topics() if eng.topic_status(t.id) != "done"), None)
    key = first.id if first else None
if not key:
    st.success("다섯 학습 주제를 모두 마쳤어요. 진단 결과를 확인해 보세요.")
    if st.button("진단 결과 보기", type="primary"):
        st.switch_page("views/result.py")
    st.stop()

try:
    session = eng.start(key)
except LearningError as e:
    st.warning(str(e))
    st.stop()
save(eng)

bundle = eng.bundle(session)
pack = eng.pack(session)
eyebrow = "집중 보충" if bundle.kind == "supplement" else f"학습 주제 {bundle.order}"
page_header(bundle.title, bundle.goal, eyebrow=eyebrow)


def go(target_key: str | None, page: str = "views/lesson.py") -> None:
    if target_key:
        st.session_state["lesson_key"] = target_key
    st.switch_page(page)


# ---------- 완료 화면 ----------
if session.status == "done":
    done_msgs = [m.text for ss in session.steps.values() for m in ss.messages
                 if m.kind == "done" and "기록해 두고" not in m.text and "기록해 둘게요" not in m.text]
    later = [s for s in session.steps.values() if s.status == "done" and s.level is not None and s.level < 3]
    with card("done"):
        html('<div class="nx-label">이번 활동에서 확인된 것</div>')
        bullet_list(list(dict.fromkeys(done_msgs)) or ["이번 활동을 끝까지 진행했어요."])
        if later or any(s.level is None and s.status == "done" for s in session.steps.values()):
            html('<p style="color:var(--text-muted);margin:.8rem 0 0">도움을 받아 해낸 부분과 아직 확인하지 못한 '
                 '부분은 다음 활동이나 새 글에서 혼자 해 보며 다시 확인해요.</p>')
    with st.expander("내가 쓴 답 다시 보기"):
        for step in bundle.steps:
            ss = session.steps.get(step.id)
            if not ss or not ss.attempts:
                continue
            html(f'<div class="nx-card-title" style="margin-top:.6rem">{_e(step.title)}</div>')
            for a in ss.attempts:
                tag = "처음 답" if a.kind == "first" else "고친 답"
                html(f'<p style="margin:.2rem 0"><b>{tag}</b> · {_e(a.text)}</p>')
    c1, c2 = st.columns(2)
    if bundle.next and bundle.kind == "topic":
        nb = pack.bundles[bundle.next]
        if c1.button(f"다음 활동 · {nb.title}", type="primary", width="stretch"):
            go(nb.id)
    elif eng.all_topics_done() or bundle.kind == "supplement":
        if c1.button("진단 결과 보기", type="primary", width="stretch"):
            go(None, "views/result.py")
    if c2.button("홈으로", width="stretch"):
        go(None, "views/home.py")
    st.stop()

# ---------- 진행 중 ----------
step = eng.current_step(session)
ss = eng.step_state(session)

dots = []
for i, s in enumerate(bundle.steps):
    st_ = session.steps.get(s.id)
    dots.append("current" if i == session.step_idx else
                (st_.status if st_ and st_.status in ("done", "skipped") else "todo"))
step_dots(dots)
if session.step_idx == 0 and not ss.attempts and bundle.intro:
    st.info(bundle.intro, icon="🧭")

left, right = st.columns([1.05, 1], gap="large")

with left:
    for ex_id in step.excerpts:
        if ex_id in eng.suspended:
            st.warning("이 제시문은 지금 점검 중이에요. 선생님께 알려 주세요.")
            continue
        passage(pack.excerpts[ex_id])
    carried = eng.carry(session, step)
    if carried:
        with st.expander("앞에서 쓴 내 답", expanded=step.kind in ("outline", "draft")):
            for title, first, final in carried:
                html(f'<div class="nx-card-title" style="font-size:.95rem;margin-top:.5rem">{_e(title)}</div>')
                if first and first.strip() != final.strip():
                    html(f'<p style="margin:.1rem 0;color:var(--text-muted)"><b>처음 답</b> · {_e(first)}</p>')
                    html(f'<p style="margin:.1rem 0"><b>고친 답</b> · {_e(final)}</p>')
                else:
                    html(f'<p style="margin:.1rem 0">{_e(final)}</p>')

with right:
    task_box(step.title, step.prompt, session.step_idx + 1, len(bundle.steps))
    if step.sentence:
        interpretation(step.sentence)
    if step.review_questions:
        bullet_list(step.review_questions, kind="todo")
    if step.kind == "draft":
        st.caption("✍️ 쓰는 동안에는 내용 도움이 없어요. 글자 수, 저장, 제시문과 내 답 다시 보기만 할 수 있어요.")
    if step.independent_check or step.allow_one_direction:
        st.caption("🔎 이번 과제는 혼자 해 보는 확인이에요. 내용 힌트는 주지 않아요.")
    dialog = step.kind in ("task", "judge")
    opening = None
    if dialog:
        opening = ("새 글이에요. 이번에는 혼자 해 보는 확인이라 내용 힌트 없이 진행해요. 제시문을 읽고 답해 보세요."
                   if step.independent_check or step.allow_one_direction else
                   "제시문을 읽고 위 과제에 답해 보세요. 답이 아니어도 괜찮아요. 낱말 뜻이나 과제가 궁금하면 "
                   "물어봐요. 정답은 먼저 알려 주지 않지만, 내 답을 보고 함께 생각해 볼게요.")
    preface = None
    if not ss.messages:
        for prev in reversed(bundle.steps[:session.step_idx]):
            pst = session.steps.get(prev.id)
            if pst and pst.status == "done":
                dm = [m.text for m in pst.messages if m.kind == "done"]
                preface = dm[-1] if dm else None
                break
    chat(ss.messages, opening=opening, preface=preface)

    real = answered(ss)
    akey = f"{session.key}_{step.id}_{len(ss.attempts)}"
    default = session.outputs.get(step.id) or (real[-1].text if real else "")
    choice, evidence = None, ""
    label = {"outline": "개요", "draft": "초고", "self_review": "점검한 글",
             "judge": "이유 (또는 궁금한 점)"}.get(step.kind, "내 답 (또는 궁금한 점)")
    height = 260 if step.kind in ("draft", "self_review") or step.max_chars else 110
    submit_label = {"outline": "개요 저장", "draft": "초고 저장", "self_review": "점검 마치기"}.get(
        step.kind, "보내기")

    # 작성창: 문답 단계에서는 직전 답을 그대로 고쳐 쓸 수 있게 채워 둔다 (Z-009)
    with st.container(key="composer") if dialog else st.container():
        if step.kind == "judge":
            prev = real[-1].choice if real else None
            choice = st.radio("판단", step.choices, horizontal=True, key=f"c_{akey}",
                              index=step.choices.index(prev) if prev in step.choices else None)
        answer = st.text_area(label, value=default, height=height, key=f"a_{akey}",
                              placeholder="여기에 직접 써 보세요.")
        if step.max_chars:
            char_meter(count_chars(answer), step.max_chars)
        if step.evidence:
            evidence = st.text_input("근거가 된 부분", key=f"e_{akey}",
                                     placeholder="예) 둘째 문단의 ‘…’ 부분",
                                     value=real[-1].evidence if real else "")
        if step.kind == "self_review":
            evidence = st.text_input("크게 고친 곳이 있다면 이유 (선택)", key=f"n_{akey}")
        b1, b2 = st.columns([1.6, 1])
        send = b1.button(submit_label, type="primary", width="stretch", icon=":material/send:")
        leave = b2.button("저장하고 나가기", width="stretch", icon=":material/bookmark:")

    if send:
        try:
            with st.spinner("답을 살펴보고 있어요…"):
                eng.submit(session, answer, evidence, choice)
            save(eng)
            st.rerun()
        except LearningError as e:
            st.warning(str(e))
    if leave:
        eng.save_draft(session, answer)
        eng.pause(session)
        save(eng)
        go(None, "views/home.py")

    opts = eng.help_options(session)
    if opts:
        html('<div class="nx-label" style="margin-top:1rem">필요한 도움</div>')
        cols = st.columns(len(opts))
        for col, opt in zip(cols, opts, strict=True):
            with col:
                if opt == "vocab":
                    with st.popover("어휘 뜻", width="stretch"):
                        word = st.selectbox("낱말", list(step.vocab), key=f"v_{akey}")
                        if st.button("뜻 보기", key=f"vb_{akey}"):
                            eng.request_help(session, "vocab", word)
                            save(eng)
                            st.rerun()
                else:
                    text = {"guide": "과제 뜻 알려 주세요", "structure": "비교표 쓰기",
                            "dont_know": "잘 모르겠어요"}[opt]
                    if st.button(text, key=f"h_{opt}_{akey}", width="stretch"):
                        eng.request_help(session, opt)
                        save(eng)
                        st.rerun()
