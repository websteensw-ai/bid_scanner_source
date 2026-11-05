"""선택 복습 (L1-028~035, L2-031~041). 추천만으로 이동하거나 중단하지 않고, 학생이 고른다.
열람 시 설명과 별도 사례 시범을 먼저 주고, 현재 제시문의 완성 답안은 공개하지 않는다."""
import streamlit as st

from src.learning.state import ReviewRecord
from src.services import auth_service
from src.services.learning_service import my_engine, save
from src.ui.components import _e, card, html, page_header

user = auth_service.require_login("student")
eng = my_engine()
pack = eng.pack()

page_header("선택 복습", "필요할 때만 골라서 보는 짧은 복습이에요. 하지 않아도 학습은 이어 갈 수 있어요.",
            eyebrow="📖 복습")

recommended = {}
for r in eng.state.reviews:
    if r.action == "recommended":
        recommended.setdefault(r.item, r.reason)
topic_names = {t.id: t.title for t in pack.topics()}
items = sorted(pack.review_items.values(),
               key=lambda i: (i.id not in recommended, i.topic, [int(x) for x in i.id.split("-")]))

sel = st.session_state.get("review_item")
if sel and sel in pack.review_items:
    item = pack.review_items[sel]
    if not any(r.item == sel and r.action == "opened" for r in eng.state.reviews[-3:]):
        eng.state.reviews.append(ReviewRecord(item=sel, action="opened", reason="학생이 선택",
                                              origin=st.session_state.get("lesson_key", "")))
        save(eng)
    with card("review_open"):
        html(f'<div class="nx-label">{_e(topic_names.get(item.topic, ""))}</div>'
             f'<div class="nx-card-title" style="font-size:1.25rem">{_e(item.name)}</div>'
             f'<p class="nx-prompt">{_e(item.explanation)}</p>')
        html(f'<div class="nx-msg tutor demo" style="max-width:100%"><div class="tag">시범 (다른 예)</div>'
             f'<div>{_e(item.demo)}</div></div>')
        if item.practice:
            html(f'<div class="nx-label" style="margin-top:1rem">짧게 적용해 보기</div><p>{_e(item.practice)}</p>')
            txt = st.text_area("내 답", key=f"rp_{sel}", height=100)
            if st.button("저장", key=f"rps_{sel}") and txt.strip():
                eng.state.reviews.append(ReviewRecord(item=sel, action="practiced", reason=txt[:200]))
                save(eng)
                st.success("저장했어요.")
    c1, c2 = st.columns(2)
    if c1.button("목록으로", width="stretch"):
        st.session_state.pop("review_item")
        st.rerun()
    if st.session_state.get("lesson_key") and c2.button("하던 학습으로 돌아가기", width="stretch",
                                                        type="primary"):
        st.session_state.pop("review_item")
        st.switch_page("views/lesson.py")
    st.stop()

if recommended:
    st.caption("✨ 표시는 내 답에서 보인 어려움과 관련된 추천이에요. 추천은 실패나 미숙달을 뜻하지 않아요.")
cols = st.columns(2, gap="medium")
for i, item in enumerate(items):
    with cols[i % 2], card(f"ri_{item.id}"):
        star = "✨ " if item.id in recommended else ""
        html(f'<div class="nx-card-meta"><span>{_e(topic_names.get(item.topic, ""))}</span></div>'
             f'<div class="nx-card-title" style="margin-top:.3rem">{star}{_e(item.name)}</div>'
             + (f'<p style="color:var(--text-muted);margin:0;font-size:.88rem">{_e(recommended[item.id])}</p>'
                if item.id in recommended else ""))
        b1, b2 = st.columns(2)
        if b1.button("지금 보기", key=f"open_{item.id}", width="stretch"):
            st.session_state["review_item"] = item.id
            st.rerun()
        if b2.button("저장해 두기", key=f"save_{item.id}", width="stretch"):
            eng.state.reviews.append(ReviewRecord(item=item.id, action="saved", reason="나중에 보기"))
            save(eng)
            st.toast("저장해 두었어요.")
