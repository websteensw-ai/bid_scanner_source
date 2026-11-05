"""학습 기록 저장소.

- DemoLearningRepo: 테스트 로그인용. 브라우저 세션(st.session_state)에만 보관
- SupabaseLearningRepo: learner_states(학생별 상태 jsonb) + content_status(사용 중지 목록)

학생 한 명의 상태는 LearnerState 하나로 저장한다 (state.py 참고).
"""
from datetime import UTC, datetime

import streamlit as st

from src.learning.state import LearnerState


class LearningRepo:
    def load(self, student_id: str) -> LearnerState:
        raise NotImplementedError

    def save(self, state: LearnerState) -> None:
        raise NotImplementedError

    def list_students(self) -> list[dict]:
        raise NotImplementedError

    def suspended(self) -> dict[str, str]:
        """사용 중지된 묶음·제시문 id → 사유 (P-014)."""
        raise NotImplementedError

    def set_status(self, item_id: str, status: str, note: str, by: str) -> None:
        raise NotImplementedError


class DemoLearningRepo(LearningRepo):
    def _bucket(self) -> dict:
        return st.session_state.setdefault("demo_learning", {"states": {}, "status": {}})

    def load(self, student_id):
        raw = self._bucket()["states"].get(student_id)
        return LearnerState.model_validate(raw) if raw else LearnerState(student_id=student_id)

    def save(self, state):
        self._bucket()["states"][state.student_id] = state.model_dump(mode="json")

    def list_students(self):
        user = st.session_state.get("user") or {}
        return [{"id": sid, "full_name": user.get("full_name", "테스트 사용자")}
                for sid in self._bucket()["states"]] or \
               [{"id": user.get("id", ""), "full_name": user.get("full_name", "테스트 사용자")}]

    def suspended(self):
        return {k: v["note"] for k, v in self._bucket()["status"].items() if v["status"] == "suspended"}

    def set_status(self, item_id, status, note, by):
        self._bucket()["status"][item_id] = {"status": status, "note": note, "by": by,
                                             "ts": datetime.now(UTC).isoformat()}


class SupabaseLearningRepo(LearningRepo):
    def __init__(self, db):
        self.db = db

    def load(self, student_id):
        rows = (self.db.table("learner_states").select("state")
                .eq("student_id", student_id).limit(1).execute().data)
        return LearnerState.model_validate(rows[0]["state"]) if rows else LearnerState(student_id=student_id)

    def save(self, state):
        self.db.table("learner_states").upsert({
            "student_id": state.student_id, "state": state.model_dump(mode="json"),
        }).execute()

    def list_students(self):
        return (self.db.table("profiles").select("id, full_name, email")
                .eq("role", "student").order("full_name").execute().data)

    def suspended(self):
        rows = self.db.table("content_status").select("*").eq("status", "suspended").execute().data
        return {r["item_id"]: r.get("note", "") for r in rows}

    def set_status(self, item_id, status, note, by):
        self.db.table("content_status").upsert({
            "item_id": item_id, "status": status, "note": note, "updated_by": by,
        }).execute()


def get_learning_repo() -> LearningRepo:
    user = st.session_state.get("user") or {}
    if user.get("is_demo"):
        return DemoLearningRepo()
    from src.db.client import get_supabase

    return SupabaseLearningRepo(get_supabase())
