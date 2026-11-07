"""교사·운영자: 학습 기록과 판정 검토 (Z-044: 내부 평가표·상태 코드는 이 화면에만).
기준별 수준과 근거, 지원 이력, 최초 답·수정 답, 검토 요청, 교사 수정 (Z-048)."""
import streamlit as st

from src.db.learning_repo import get_learning_repo
from src.learning.levels import CRITERION_LABEL, SUPPORT_LABEL, Criterion, SupportType, level_label
from src.services import auth_service
from src.services.learning_service import engine_for, save
from src.ui.components import _e, card, html, page_header, stat_grid

user = auth_service.require_login("teacher", "admin")

page_header("학습 기록", "기준별 수준과 근거, 받은 도움, 최초 답과 수정 답, 검토 요청을 확인하고 판정을 수정해요.",
            eyebrow="🧑‍🏫 교사·운영자")

students = get_learning_repo().list_students()
if not students:
    st.info("아직 학습 기록이 있는 학생이 없어요.")
    st.stop()
stu = st.selectbox("학생", students, format_func=lambda s: s.get("full_name") or s.get("email") or s["id"])
eng = engine_for(stu["id"])
state = eng.state
pack = eng.pack()


def lvl_html(level):
    cls = "ln" if level is None else f"l{level}"
    return f'<span class="nx-level {cls}">{_e(level_label(level))}</span>'


entry = eng.latest_entry()
open_flags = [f for f in state.flags if not f.resolved]
stat_grid([
    ("📚", "마친 학습 주제", f"{sum(eng.topic_status(t.id) == 'done' for t in pack.topics())}", "/ 5"),
    ("🧭", "최근 진입 판정", entry["decision"] if entry else "–", ""),
    ("🚩", "검토 요청", f"{len(open_flags)}", "건"),
])

tab_c, tab_s, tab_f, tab_e = st.tabs(["기준별 판정", "활동 기록", "검토 요청", "이벤트"])

with tab_c:
    html("".join(
        f'<div class="nx-crit"><div class="head"><span class="name">{_e(CRITERION_LABEL[c])}</span>'
        f'{lvl_html(state.criteria[c.value].level if c.value in state.criteria else None)}</div>'
        + (f'<div class="cmt">근거: {_e(state.criteria[c.value].source)} · 지원: '
           f'{_e(", ".join(SUPPORT_LABEL[SupportType(x)] for x in state.criteria[c.value].supports) or "없음")}'
           f' · 버전 {_e(state.criteria[c.value].version)}'
           + (f' · 교사 수정: {_e(state.criteria[c.value].note)}' if state.criteria[c.value].by == "teacher" else "")
           + f'<br>응답: {_e(state.criteria[c.value].evidence)}</div>'
           if c.value in state.criteria else '<div class="cmt">아직 증거 없음 (미확인)</div>')
        + "</div>" for c in Criterion))
    if entry:
        st.caption(f"판정 이유(내부): {' / '.join(entry['reasons'])}")
    with st.expander("판정 수정 (교사)"):
        c = st.selectbox("기준", list(Criterion), format_func=lambda x: CRITERION_LABEL[x])
        new = st.selectbox("수준", [3, 2, 1, 0, None], format_func=level_label)
        note = st.text_input("수정 사유 (필수)")
        if st.button("수정 저장", type="primary"):
            if not note.strip():
                st.warning("수정 사유를 입력해 주세요.")
            else:
                eng.teacher_set(c.value, new, note, user.get("full_name") or user["email"])
                save(eng)
                st.success("수정했어요. 진입 판정을 같은 규칙으로 다시 적용했어요.")
                st.rerun()

with tab_s:
    if not state.sessions:
        st.info("아직 활동 기록이 없어요.")
    for s in state.sessions.values():
        b = pack.bundles.get(s.bundle_id)
        if not b:
            continue
        res = " · ".join(f"{k} {level_label(v)}" for k, v in s.result.items()) or "기준 증거 없음(기능 프로필)"
        with st.expander(f"{b.id} {b.title} — {s.status} · 버전 {s.version} · {res}"):
            if s.errors_seen:
                st.caption("보인 어려움: " + ", ".join(s.errors_seen))
            for step in b.steps:
                ss = s.steps.get(step.id)
                if not ss:
                    continue
                with card(f"rec_{s.key}_{step.id}"):
                    html(f'<div class="nx-card-meta"><b>{_e(step.title)}</b> {lvl_html(ss.level) if ss.status == "done" else ""}'
                         f'<span>{_e(ss.status)}</span><span>활동 {ss.active_seconds:.0f}초 · AI 대기 {ss.ai_wait_seconds:.1f}초</span></div>')
                    for a in ss.attempts:
                        sup = ", ".join(SUPPORT_LABEL[x] for x in a.supports_before) or "지원 없음"
                        kind_label = {"first": "최초 답", "revised": "수정 답", "off_task": "과제와 무관한 발화",
                                      "question": "질문", "answer_request": "정답 요구"}.get(a.kind, a.kind)
                        html(f'<p style="margin:.4rem 0 0"><b>{kind_label}</b>'
                             f' ({_e(sup)} 후): {_e(a.text)}'
                             + (f'<br><span style="color:var(--text-muted)">근거 표시: {_e(a.evidence)}</span>' if a.evidence else "")
                             + (f'<br><span style="color:var(--text-muted)">선택: {_e(a.choice)}</span>' if a.choice else "")
                             + f'<br><span style="color:var(--text-muted)">충족: {_e(", ".join(a.met) or "-")} · 오류: {_e(a.error or "-")} · {_e(a.rationale)}</span></p>')
                    for sp in ss.supports:
                        html(f'<p style="margin:.2rem 0;color:var(--text-secondary)">↳ {_e(SUPPORT_LABEL[sp.type])}'
                             f' [{_e(sp.point)}]: {_e(sp.text[:140])}</p>')

with tab_f:
    if not state.flags:
        st.info("검토 요청이 없어요.")
    KIND = {"uncertain": "판정 불확실", "repeat_difficulty": "같은 어려움 지속", "dispute": "학생 이의",
            "not_confirmed": "보충 후 수행 미확인", "content": "자료 문제"}
    for i, f in enumerate(state.flags):
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"{'✅' if f.resolved else '🚩'} **{KIND.get(f.kind, f.kind)}** · {f.source} · {f.detail} · {f.ts[:16]}")
        if not f.resolved and c2.button("처리 완료", key=f"flag_{i}"):
            f.resolved = True
            state.log("flag_resolved", f.source, kind=f.kind, by=user["email"])
            save(eng)
            st.rerun()

with tab_e:
    st.dataframe([{"시각": e.ts[:19], "종류": e.type, "위치": e.source, "내용": str(e.payload)[:120]}
                  for e in reversed(state.events)], width="stretch", hide_index=True)
