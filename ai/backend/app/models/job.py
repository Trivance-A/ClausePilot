import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Job(Base):
    """문서 처리(process_document), 규정 인덱싱(index_regulation), 평가 실행(eval)에 공용으로 쓰는 작업 테이블.
    job_type: process_document|index_regulation|eval. status: QUEUED|RUNNING|DONE|FAILED.
    target_id는 job_type에 따라 documents.id / regulations.id / eval_runs.id 중 하나를 가리키는 다형 참조라
    DB 레벨 FK 제약은 걸지 않는다. current_step: normalize|ocr|extract|risk (문서) 등 문자열."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="QUEUED")
    current_step: Mapped[str | None] = mapped_column(String, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
