"""로그인 사용자에 맞는 저장소(Supabase 또는 테스트용 인메모리)를 반환."""
from dataclasses import dataclass
from typing import Any

import streamlit as st


@dataclass
class Repos:
    assignments: Any
    essays: Any
    feedbacks: Any


def is_demo_session() -> bool:
    user = st.session_state.get("user") or {}
    return bool(user.get("is_demo"))


def get_repos() -> Repos:
    if is_demo_session():
        from src.db.demo_store import DemoAssignmentRepo, DemoEssayRepo, DemoFeedbackRepo

        return Repos(DemoAssignmentRepo(), DemoEssayRepo(), DemoFeedbackRepo())

    from src.db.client import get_supabase
    from src.db.repositories import AssignmentRepo, EssayRepo, FeedbackRepo

    db = get_supabase()
    return Repos(AssignmentRepo(db), EssayRepo(db), FeedbackRepo(db))
