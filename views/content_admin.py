"""교사·운영자: 자료 관리 (P-005·P-014·P-015·P-018·L1-021·L3-061~067).
제시문의 내부 출처 정보는 이 화면에서만 보인다. 사실 오류나 부적합 과제는 즉시 사용 중지할 수 있다."""
import streamlit as st

from src.db.learning_repo import get_learning_repo
from src.learning.content import active_version, available_versions, load_pack
from src.services import auth_service
from src.ui.components import _e, card, html, page_header, stat_grid

user = auth_service.require_login("teacher", "admin")
repo = get_learning_repo()
suspended = repo.suspended()

page_header("자료 관리", "제시문·학습 묶음의 버전과 승인 상태를 확인하고, 문제가 있으면 즉시 사용을 중지해요.",
            eyebrow="🗂️ 교사·운영자")

ver = st.selectbox("콘텐츠 버전", available_versions(), index=available_versions().index(active_version()),
                   help="새 학습 배정에는 활성 버전이 쓰이고, 진행 중인 학습은 시작할 때의 버전을 유지해요.")
pack = load_pack(ver)
stat_grid([
    ("🏷️", "활성 버전", active_version(), ""),
    ("📄", "제시문", f"{len(pack.excerpts)}", "개"),
    ("🧩", "학습 묶음", f"{len(pack.bundles)}", "개"),
    ("⛔", "사용 중지", f"{len(suspended)}", "건"),
])
st.caption("현재 제시문은 모두 **시범용 신규 설계문**이에요. 운영 전에 승인된 발췌문으로 교체해야 해요.")

KIND = {"lesson": "기본 제시문", "demo": "설명·시범용", "independent": "독립 확인용", "recheck": "보충 재확인용",
        "practice": "연습용"}
tab_b, tab_x = st.tabs(["학습 묶음", "제시문"])


def toggle(item_id: str) -> None:
    if item_id in suspended:
        if st.button("사용 재개", key=f"on_{item_id}"):
            repo.set_status(item_id, "approved", "", user["email"])
            st.rerun()
    else:
        with st.popover("사용 중지"):
            note = st.text_input("사유", key=f"why_{item_id}")
            if st.button("중지", key=f"off_{item_id}", type="primary") and note.strip():
                repo.set_status(item_id, "suspended", note, user["email"])
                st.rerun()


with tab_b:
    for b in sorted(pack.bundles.values(), key=lambda x: (x.kind != "topic", x.order, x.id)):
        with card(f"b_{b.id}"):
            stt = "⛔ 사용 중지 · " + suspended[b.id] if b.id in suspended else f"✅ {b.status}"
            html(f'<div class="nx-card-meta"><b>{_e(b.id)}</b><span>{_e(stt)}</span>'
                 f'<span>활동 {len(b.steps)}개</span><span>{_e(b.time_target)}</span></div>'
                 f'<div class="nx-card-title" style="margin-top:.3rem">{_e(b.title)}'
                 + (f' · {_e(b.path_name)}' if b.path_name else "") + '</div>'
                 f'<p style="color:var(--text-muted);margin:0;font-size:.9rem">{_e(b.goal)}</p>')
            with st.expander("활동·판단 기준·오류 대응 (내부)"):
                for s in b.steps:
                    flags = [x for x, on in (("독립 확인", s.independent_check), ("재확인", s.allow_one_direction),
                                             ("충족 시 생략", s.skip_if_met)) if on]
                    st.markdown(f"**{s.id} · {s.title}** ({s.kind}{' · ' + ', '.join(flags) if flags else ''})")
                    for c in s.criteria:
                        st.markdown(f"- 기준 `{c.id}` {'(필수)' if c.required else '(선택)'} {c.desc} → "
                                    f"{', '.join(c.evidence_for) or '기능 프로필'} · 복습 {c.skill or '-'}")
                    for e in s.errors:
                        if e.first_question:
                            st.markdown(f"- 오류 `{e.id}` {e.name}: “{e.first_question}”")
            toggle(b.id)

with tab_x:
    for ex in pack.excerpts.values():
        used = [f"{b.id}/{s.id}" for b in pack.bundles.values() for s in b.steps
                if ex.id in s.excerpts or (s.demo and s.demo.excerpt == ex.id)]
        with card(f"x_{ex.id}"):
            stt = "⛔ 사용 중지 · " + suspended[ex.id] if ex.id in suspended else f"✅ {ex.status}"
            html(f'<div class="nx-card-meta"><b>{_e(ex.id)}</b><span>학생 표기 {_e(ex.label)}</span>'
                 f'<span>{_e(KIND.get(ex.kind, ex.kind))}</span><span>{_e(stt)}</span></div>'
                 f'<p style="margin:.5rem 0 .2rem"><b>내부 출처</b> · {_e(ex.source.title)} '
                 f'{_e(ex.source.author)} · {_e(ex.source.location)}'
                 + (' · <b style="color:var(--warning)">시범용 신규 설계문</b>' if ex.source.is_sample else "")
                 + f'</p><p style="color:var(--text-muted);margin:0;font-size:.88rem">{_e(ex.source.note)}</p>'
                 f'<p style="color:var(--text-muted);margin:.2rem 0 0;font-size:.85rem">사용 위치: {_e(", ".join(used))}</p>')
            with st.expander("본문 보기"):
                for p in ex.paragraphs:
                    st.write(p)
            toggle(ex.id)
