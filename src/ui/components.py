"""재사용 UI 컴포넌트."""
import streamlit as st

from src.core.models import FeedbackResult


def char_counter(text: str, min_chars: int, max_chars: int) -> bool:
    n = len(text.replace(" ", "").replace("\n", ""))
    ok = min_chars <= n <= max_chars
    (st.success if ok else st.info)(f"공백 제외 {n:,}자 / 권장 {min_chars:,}~{max_chars:,}자")
    return ok


def render_feedback(fb: FeedbackResult) -> None:
    st.metric("총점", f"{fb.total_score} / 100")
    st.write(fb.summary)

    cols = st.columns(len(fb.criteria))
    for col, c in zip(cols, fb.criteria, strict=False):
        col.metric(c.criterion, f"{c.score}/10")
        col.caption(c.comment)

    left, right = st.columns(2)
    with left:
        st.subheader("👍 잘한 점")
        for s in fb.strengths:
            st.markdown(f"- {s}")
    with right:
        st.subheader("🛠 보완할 점")
        for s in fb.improvements:
            st.markdown(f"- {s}")

    if fb.corrections:
        st.subheader("✏️ 문장 첨삭")
        for c in fb.corrections:
            with st.container(border=True):
                st.markdown(f"~~{c.original}~~  \n→ **{c.suggestion}**")
                st.caption(c.reason)
