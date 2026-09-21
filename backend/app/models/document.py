import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String)
    source_format: Mapped[str] = mapped_column(String)  # hwp / hwpx / pdf / xlsx
    normalized_pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    ocr_blocks: Mapped[list["OcrBlock"]] = relationship(back_populates="document")
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(back_populates="document")
    risk_flags: Mapped[list["RiskFlag"]] = relationship(back_populates="document")


class OcrBlock(Base):
    __tablename__ = "ocr_blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    page_no: Mapped[int] = mapped_column(Integer)
    block_id: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    bbox: Mapped[list] = mapped_column(JSONB)  # [x0, y0, x1, y1]
    block_type: Mapped[str] = mapped_column(String)  # line / table_cell / paragraph
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="ocr_blocks")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    field_key: Mapped[str] = mapped_column(String)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_block_id: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="extracted_fields")


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    category: Mapped[str] = mapped_column(String)  # 독소조항 / 과도한위약금 / 필수항목누락 / 내용모순
    level: Mapped[str] = mapped_column(String)  # High / Medium / Low
    description: Mapped[str] = mapped_column(Text)
    evidence_page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="risk_flags")


class GuaranteeApplication(Base):
    __tablename__ = "guarantee_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    filled_fields: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
