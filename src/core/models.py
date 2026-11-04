"""도메인 모델 (DB 테이블 및 AI 응답 스키마)."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class EssayStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"


class Profile(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None
    role: Role = Role.STUDENT


class Assignment(BaseModel):
    id: UUID
    title: str
    prompt: str                      # 논제
    min_chars: int = 800
    max_chars: int = 1600
    due_at: datetime | None = None
    created_by: UUID | None = None


class Essay(BaseModel):
    id: UUID | None = None
    student_id: UUID
    assignment_id: UUID
    content: str = ""
    status: EssayStatus = EssayStatus.DRAFT
    submitted_at: datetime | None = None


# ---- AI 피드백 스키마 ----
class CriterionScore(BaseModel):
    criterion: str = Field(description="평가 항목명")
    score: int = Field(ge=0, le=10)
    comment: str


class InlineCorrection(BaseModel):
    original: str = Field(description="원문 구절")
    suggestion: str = Field(description="수정 제안")
    reason: str


class FeedbackResult(BaseModel):
    total_score: int = Field(ge=0, le=100)
    criteria: list[CriterionScore]
    strengths: list[str]
    improvements: list[str]
    corrections: list[InlineCorrection] = []
    summary: str
