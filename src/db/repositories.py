"""테이블별 CRUD. UI/서비스 계층은 Supabase 쿼리를 직접 쓰지 않고 여기를 거칩니다."""
from datetime import UTC, datetime
from typing import Any

from supabase import Client

from src.core.models import EssayStatus, FeedbackResult


class AssignmentRepo:
    def __init__(self, db: Client):
        self.db = db

    def list_open(self) -> list[dict[str, Any]]:
        return (self.db.table("assignments").select("*")
                .order("created_at", desc=True).execute().data)

    def create(self, title: str, prompt: str, min_chars: int, max_chars: int, created_by: str):
        return self.db.table("assignments").insert({
            "title": title, "prompt": prompt, "min_chars": min_chars,
            "max_chars": max_chars, "created_by": created_by,
        }).execute().data


class EssayRepo:
    def __init__(self, db: Client):
        self.db = db

    def get_or_create_draft(self, student_id: str, assignment_id: str) -> dict[str, Any]:
        res = (self.db.table("essays").select("*")
               .eq("student_id", student_id).eq("assignment_id", assignment_id)
               .limit(1).execute())
        if res.data:
            return res.data[0]
        return self.db.table("essays").insert({
            "student_id": student_id, "assignment_id": assignment_id,
        }).execute().data[0]

    def save(self, essay_id: str, content: str) -> None:
        self.db.table("essays").update({"content": content}).eq("id", essay_id).execute()

    def submit(self, essay_id: str, content: str) -> None:
        self.db.table("essays").update({
            "content": content,
            "status": EssayStatus.SUBMITTED,
            "submitted_at": datetime.now(UTC).isoformat(),
        }).eq("id", essay_id).execute()

    def list_by_student(self, student_id: str) -> list[dict[str, Any]]:
        return (self.db.table("essays").select("*, assignments(title), feedbacks(*)")
                .eq("student_id", student_id).order("updated_at", desc=True).execute().data)

    def list_submitted(self) -> list[dict[str, Any]]:
        return (self.db.table("essays")
                .select("*, assignments(title), profiles(full_name, email), feedbacks(*)")
                .neq("status", EssayStatus.DRAFT).order("submitted_at", desc=True).execute().data)


class FeedbackRepo:
    def __init__(self, db: Client):
        self.db = db

    def create(self, essay_id: str, result: FeedbackResult, provider: str, model: str) -> None:
        self.db.table("feedbacks").insert({
            "essay_id": essay_id,
            "total_score": result.total_score,
            "result": result.model_dump(),
            "provider": provider,
            "model": model,
        }).execute()
        # essays.status -> 'reviewed' 전환은 DB 트리거(mark_essay_reviewed)가 처리
