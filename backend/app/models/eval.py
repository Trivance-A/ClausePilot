import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvalRun(Base):
    """suite: extraction|retrieval|faithfulness|all. status: QUEUED|RUNNING|DONE|FAILED.
    metrics: {field_accuracy:{overall, by_field}, bbox_mapping_rate, recall_at_5, hallucination_rate} (성능 목표 실측치).
    failures: [{doc_id, doc_name?, field_code, expected, got}] — 정확도 미달 사례 목록."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suite: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="QUEUED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    failures: Mapped[list] = mapped_column(JSONB, default=list)
