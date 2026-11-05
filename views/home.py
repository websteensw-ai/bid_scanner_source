import streamlit as st

from src.learning.levels import CRITERION_PLAIN, Criterion
from src.services import auth_service
from src.services.learning_service import my_engine
from src.ui.components import _e, card, chip, hero, html, stat_grid

user = auth_service.require_login("student")
eng = my_engine()
pack = eng.pack()
topics = pack.topics()
name = user.get("full_name") or user["email"]

status = {t.id: eng.topic_status(t.id) for t in topics}
current = next((t for t in topics if status[t.id] in ("active", "paused")), None) \
    or next((t for t in topics if status[t.id] == "todo"), None)

hero(f"{name} 님, 오늘의 목표" if current else f"{name} 님, 기초 다지기를 모두 마쳤어요",
     current.goal if current else "진입 준비 결과에서 지금 할 수 있는 것과 다음 학습을 확인해 보세요.",
     eyebrow="기초 다지기")

done_n = sum(v == "done" for v in status.values())
entry = eng.latest_entry()
strong = [c for c in Criterion
          if eng.state.criteria.get(c.value) and (eng.state.criteria[c.value].level or 0) >= 2]
stat_grid([
    ("📚", "마친 학습 주제", f"{done_n}", f"/ {len(topics)}"),
    ("✅", "할 수 있게 된 것", f"{len(strong)}", "가지"),
    ("🧭", "다음 활동", current.title if current else "결과 확인", ""),
])

if current:
    c1, c2 = st.columns([1, 2])
    label = "이어서 하기" if status[current.id] in ("active", "paused") else "시작하기"
    if c1.button(f"{label} · {current.title}", type="primary", width="stretch",
                 icon=":material/play_arrow:"):
        st.session_state["lesson_key"] = current.id
        st.switch_page("views/lesson.py")
if entry:
    st.info("진입 준비 결과가 나왔어요. **진단 결과**에서 확인해 보세요.", icon="🧭")

if strong:
    html('<h3 style="margin:1.6rem 0 .6rem;font-size:1.15rem">할 수 있게 된 것</h3>')
    html('<ul class="nx-list good">' + "".join(
        f'<li data-i="✓">{_e(CRITERION_PLAIN[c])}</li>' for c in strong) + "</ul>")

html('<h3 style="margin:1.6rem 0 .8rem;font-size:1.15rem">다섯 학습 주제</h3>')
for t in topics:
    stt = status[t.id]
    with card(f"topic_{t.id}"):
        html(f'<div class="nx-topic {stt}"><div class="num">{t.order}</div><div style="flex:1">'
             f'<div class="nx-card-meta">{chip(stt)}<span>약 {_e(t.time_target)}</span></div>'
             f'<div class="nx-card-title" style="margin-top:.45rem">{_e(t.title)}</div>'
             f'<p style="color:var(--text-muted);margin:0;font-size:.92rem">{_e(t.goal)}</p></div></div>')
        if stt in ("active", "paused") or (stt == "todo" and t is current):
            if st.button("이어서 하기" if stt != "todo" else "시작하기", key=f"go_{t.id}",
                         width="stretch"):
                st.session_state["lesson_key"] = t.id
                st.switch_page("views/lesson.py")
        elif stt == "done":
            if st.button("내 답 다시 보기", key=f"see_{t.id}", width="stretch"):
                st.session_state["lesson_key"] = t.id
                st.switch_page("views/lesson.py")

active_supp = [s for s in eng.state.sessions.values()
               if s.bundle_id.startswith("S") and s.status != "done"]
if active_supp:
    html('<h3 style="margin:1.6rem 0 .8rem;font-size:1.15rem">진행 중인 보충</h3>')
    for s in active_supp:
        b = pack.bundles[s.bundle_id]
        if st.button(f"이어서 하기 · {b.title}", key=f"supp_{s.key}"):
            st.session_state["lesson_key"] = s.key
            st.switch_page("views/lesson.py")
