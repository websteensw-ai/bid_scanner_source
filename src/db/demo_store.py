"""테스트 로그인용 인메모리 저장소.

Supabase 리포지토리(repositories.py)와 같은 메서드·반환 형태를 제공하므로
페이지/서비스 코드는 어느 쪽인지 몰라도 됩니다. 데이터는 브라우저 세션마다
따로 보관되며 새로고침(세션 종료) 시 초기화됩니다.
"""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import streamlit as st

from src.core.models import EssayStatus, FeedbackResult

DEMO_USER_ID = "00000000-0000-0000-0000-00000000test"

_SEED_ASSIGNMENTS = [
    {
        "title": "AI와 인간의 창의성",
        "prompt": "생성형 AI가 만든 작품을 인간의 창작물과 동등하게 볼 수 있는가? "
                  "자신의 입장을 정하고 근거를 들어 논술하시오.",
        "min_chars": 800, "max_chars": 1600,
    },
    {
        "title": "기본소득 도입의 타당성",
        "prompt": "자동화로 일자리가 줄어드는 사회에서 기본소득 제도의 도입이 타당한지 "
                  "찬반 입장을 정하여 논술하시오.",
        "min_chars": 600, "max_chars": 1200,
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _store() -> dict[str, Any]:
    if "demo_store" not in st.session_state:
        st.session_state["demo_store"] = {
            "assignments": [
                {"id": str(uuid4()), "created_by": DEMO_USER_ID, "created_at": _now(), **a}
                for a in _SEED_ASSIGNMENTS
            ],
            "essays": [],
            "feedbacks": [],
        }
    return st.session_state["demo_store"]


def _with_relations(e: dict[str, Any]) -> dict[str, Any]:
    s = _store()
    a = next((x for x in s["assignments"] if x["id"] == e["assignment_id"]), None)
    return {
        **e,
        "assignments": {"title": a["title"]} if a else None,
        "profiles": {"full_name": "테스트 사용자", "email": "test"},
        "feedbacks": [f for f in s["feedbacks"] if f["essay_id"] == e["id"]],
    }


class DemoAssignmentRepo:
    def list_open(self) -> list[dict[str, Any]]:
        return sorted(_store()["assignments"], key=lambda a: a["created_at"], reverse=True)

    def create(self, title: str, prompt: str, min_chars: int, max_chars: int, created_by: str):
        row = {"id": str(uuid4()), "title": title, "prompt": prompt, "min_chars": min_chars,
               "max_chars": max_chars, "created_by": created_by, "created_at": _now()}
        _store()["assignments"].append(row)
        return [row]


class DemoEssayRepo:
    def _find(self, essay_id: str) -> dict[str, Any]:
        return next(e for e in _store()["essays"] if e["id"] == essay_id)

    def get_or_create_draft(self, student_id: str, assignment_id: str) -> dict[str, Any]:
        for e in _store()["essays"]:
            if e["student_id"] == student_id and e["assignment_id"] == assignment_id:
                return e
        row = {"id": str(uuid4()), "student_id": student_id, "assignment_id": assignment_id,
               "content": "", "status": EssayStatus.DRAFT, "submitted_at": None,
               "updated_at": _now()}
        _store()["essays"].append(row)
        return row

    def save(self, essay_id: str, content: str) -> None:
        self._find(essay_id).update(content=content, updated_at=_now())

    def submit(self, essay_id: str, content: str) -> None:
        self._find(essay_id).update(content=content, status=EssayStatus.SUBMITTED,
                                    submitted_at=_now(), updated_at=_now())

    def list_by_student(self, student_id: str) -> list[dict[str, Any]]:
        rows = [e for e in _store()["essays"] if e["student_id"] == student_id]
        return [_with_relations(e) for e in sorted(rows, key=lambda e: e["updated_at"],
                                                    reverse=True)]

    def list_submitted(self) -> list[dict[str, Any]]:
        rows = [e for e in _store()["essays"] if e["status"] != EssayStatus.DRAFT]
        return [_with_relations(e) for e in sorted(rows, key=lambda e: e["submitted_at"],
                                                    reverse=True)]


class DemoFeedbackRepo:
    def create(self, essay_id: str, result: FeedbackResult, provider: str, model: str) -> None:
        s = _store()
        s["feedbacks"].append({
            "id": str(uuid4()), "essay_id": essay_id, "total_score": result.total_score,
            "result": result.model_dump(), "provider": provider, "model": model,
            "created_at": _now(),
        })
        # Supabase 쪽에서는 DB 트리거가 하는 일
        next(e for e in s["essays"] if e["id"] == essay_id)["status"] = EssayStatus.REVIEWED
