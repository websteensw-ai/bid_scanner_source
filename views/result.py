"""진입 준비 결과 (Z-037·Z-038·S2-066). 내부 판정 용어·기준 번호는 학생에게 노출하지 않는다."""
import streamlit as st

from src.learning.entry import STUDENT_MESSAGE, EntryDecision
from src.learning.levels import CRITERION_PLAIN, Criterion
from src.services import auth_service
from src.services.learning_service import my_engine, save
from src.ui.components import _e, bullet_list, card, hero, html, page_header

user = auth_service.require_login("student")
eng = my_engine()
pack = eng.pack()

page_header("진단 결과", "지금 할 수 있는 것과 도움이 필요한 부분, 다음 학습을 안내해요.", eyebrow="🧭 결과")

entry = eng.latest_entry()
if not entry:
    left = [t for t in pack.topics() if eng.topic_status(t.id) != "done"]
    st.info("다섯 학습 주제를 모두 마치면 결과를 볼 수 있어요. 하루에 모두 끝내지 않아도 괜찮아요.", icon="📚")
    bullet_list([f"{t.order}. {t.title}" for t in left], kind="todo")
    if left and st.button(f"이어서 하기 · {left[0].title}", type="primary"):
        st.session_state["lesson_key"] = left[0].id
        st.switch_page("views/lesson.py")
    st.stop()

decision = EntryDecision(entry["decision"])
levels = entry["levels"]
TITLE = {
    EntryDecision.READY: "본격 학습을 시작할 준비가 되었어요",
    EntryDecision.CONDITIONAL: "본격 학습을 시작할 수 있어요",
    EntryDecision.SUPPLEMENT: "짧은 보충 후 다시 확인해요",
    EntryDecision.HOLD: "한 번 더 확인이 필요해요",
}
hero(TITLE[decision], STUDENT_MESSAGE[decision], eyebrow="진입 준비 결과")


def how(level):
    return {3: "혼자서 해냈어요", 2: "작은 도움으로 해냈어요",
            1: "도움을 받아 해냈어요", 0: "아직 함께 연습이 필요해요"}.get(level, "아직 확인하지 못했어요")


can = [c for c in Criterion if (levels.get(c.value) or -1) >= 2]
need = [c for c in Criterion if c not in can]
c1, c2 = st.columns(2, gap="medium")
with c1, card("can"):
    html('<div class="nx-label">지금 할 수 있는 것</div>')
    bullet_list([f"{CRITERION_PLAIN[c]} — {how(levels.get(c.value))}" for c in can] or ["다음 활동에서 함께 확인해요."])
with c2, card("need"):
    html('<div class="nx-label">도움이 필요한 부분</div>')
    bullet_list([f"{CRITERION_PLAIN[c]} — {how(levels.get(c.value))}" for c in need] or ["지금은 없어요."],
                kind="todo")

with card("reason"):
    html('<div class="nx-label">이렇게 안내한 이유</div>')
    reasons = []
    if decision == EntryDecision.READY:
        reasons.append("글의 중심 생각 잡기와 주장·이유 잇기를 포함해 여러 가지를 혼자서 해냈어요.")
    if decision == EntryDecision.CONDITIONAL:
        reasons.append("다섯 가지 모두 해낼 수 있었지만, 일부는 도움을 받아 해냈어요.")
    if decision == EntryDecision.SUPPLEMENT:
        reasons.append("본격 학습에 꼭 필요한 부분 가운데 아직 도움이 많이 필요한 부분이 있어요.")
    if decision == EntryDecision.HOLD:
        reasons.append("아직 확인하지 못한 부분이 있어서, 지금은 판단하지 않고 한 번 더 확인해요. "
                       "틀렸다는 뜻이 아니에요.")
    reasons.append("점수를 더해서 정하지 않고, 실제로 쓴 답과 받은 도움을 보고 정했어요.")
    bullet_list(reasons, kind="todo")

html('<h3 style="margin:1.6rem 0 .8rem;font-size:1.15rem">다음 학습</h3>')
if decision == EntryDecision.SUPPLEMENT:
    opts = eng.supplement_options()
    if opts:
        st.caption("필요한 부분만 10~15분 정도 짧게 보충해요. 지금까지 해낸 것과 내가 쓴 답은 그대로 남아요.")
        for b in opts:
            with card(f"supp_{b.id}"):
                html(f'<div class="nx-card-title">{_e(b.title)}</div>'
                     f'<p style="color:var(--text-muted);margin:0">{_e(b.goal)}</p>')
                if st.button("보충 시작하기", key=f"start_{b.id}", type="primary"):
                    st.session_state["lesson_key"] = b.id
                    st.switch_page("views/lesson.py")
    else:
        st.info("필요한 보충을 이미 진행했어요. 같은 보충을 반복하지 않고, 선생님이 함께 살펴본 뒤 "
                "다음 방법을 안내해 줄 거예요.", icon="🧑‍🏫")
elif decision == EntryDecision.HOLD:
    missing = [Criterion(c) for c in entry["focus"]]
    st.info("확인하지 못한 부분: " + ", ".join(CRITERION_PLAIN[c] for c in missing)
            + ". 선생님이 짧은 확인 과제를 안내해 줄 거예요.", icon="🔎")
else:
    st.success("본격 학습(초급 6단계)으로 이어 갈 수 있어요. 본격 학습 과정은 준비 중이에요.", icon="🚀")
    recs = [r for r in eng.state.reviews if r.action == "recommended"]
    if recs:
        st.caption("원하면 골라서 볼 수 있는 복습이에요. 꼭 하지 않아도 본격 학습은 이어 갈 수 있어요.")
        for r in recs:
            item = pack.review_items.get(r.item)
            if item:
                st.markdown(f"- **{item.name}** — {r.reason}")
        if st.button("선택 복습 보기"):
            st.switch_page("views/review.py")

with st.expander("이 결과에 동의하지 않아요"):
    st.caption("결과의 근거가 된 내 답을 보여 줄게요. 다른 짧은 과제로 다시 확인해 달라고 요청할 수 있어요.")
    for c in Criterion:
        rec = eng.state.criteria.get(c.value)
        if rec and rec.evidence:
            html(f'<p style="margin:.3rem 0"><b>{_e(CRITERION_PLAIN[c])}</b> · {_e(rec.evidence)}</p>')
    target = st.selectbox("다시 확인하고 싶은 부분", list(Criterion), format_func=lambda c: CRITERION_PLAIN[c])
    why = st.text_area("이유 (선택)", key="dispute_why")
    if st.button("다시 확인 요청하기"):
        eng.dispute(target.value, why or "학생이 재확인을 요청함")
        save(eng)
        st.success("요청을 남겼어요. 선생님이 확인한 뒤 다른 짧은 과제로 다시 확인해요.")
