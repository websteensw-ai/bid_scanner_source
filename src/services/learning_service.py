"""화면에서 쓰는 학습 서비스. 화면은 엔진·저장소를 직접 만들지 않고 여기를 거친다."""
import streamlit as st

from src.db.learning_repo import get_learning_repo
from src.learning.analyzer import get_analyzer
from src.learning.engine import Engine


def engine_for(student_id: str) -> Engine:
    user = st.session_state.get("user") or {}
    repo = get_learning_repo()
    state = repo.load(student_id)
    return Engine(state, get_analyzer(demo=bool(user.get("is_demo"))),
                  suspended=set(repo.suspended()))


def my_engine() -> Engine:
    return engine_for(st.session_state["user"]["id"])


def save(engine: Engine) -> None:
    get_learning_repo().save(engine.state)
