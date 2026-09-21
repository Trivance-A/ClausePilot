import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

FIELD_CODES = [
    "contract_name",
    "contract_amount",
    "guarantee_amount",
    "contract_date",
    "performance_due_date",
    "guarantee_period",
    "creditor_name",
    "creditor_biz_no",
]


class Extraction(Base):
    """documents : extractions = 1:1. status: AUTO | REVIEWED | CONFIRMED
    (REVIEWED = 일부 필드 검수 완료, CONFIRMED = 전체 필드 is_confirmed=true)."""

    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    status: Mapped[str] = mapped_column(String, default="AUTO")
    model_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    fields: Mapped[list["ExtractionField"]] = relationship(back_populates="extraction")


class ExtractionField(Base):
    """field_code는 FIELD_CODES 중 하나. mapping_method: exact|fuzzy|llm_ref|manual|none.
    color_key는 프론트 color_map 조회용 키(보통 field_code와 동일)."""

    __tablename__ = "extraction_fields"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"))
    field_code: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    color_key: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    mapping_method: Mapped[str] = mapped_column(String, default="none")
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction: Mapped["Extraction"] = relationship(back_populates="fields")
    highlights: Mapped[list["Highlight"]] = relationship(back_populates="extraction_field")
