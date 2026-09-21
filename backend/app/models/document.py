import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Document(Base):
    """status: UPLOADED | NORMALIZING | OCR | EXTRACTING | RISK | DONE | FAILED
    source_type: native | scan | mixed (파싱 후 판별, 업로드 직후에는 null)
    risk_summary(요약)는 저장하지 않고 risk_findings에서 조회 시점에 집계한다."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    original_name: Mapped[str] = mapped_column(String)
    original_format: Mapped[str] = mapped_column(String)  # hwp / hwpx / pdf / xlsx / ...
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    normalized_pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="UPLOADED")
    failure_step: Mapped[str | None] = mapped_column(String, nullable=True)  # normalize/ocr/extract/risk 중 실패 단계
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    pages: Mapped[list["Page"]] = relationship(back_populates="document")
    ocr_lines: Mapped[list["OcrLine"]] = relationship(back_populates="document")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    page_no: Mapped[int] = mapped_column(Integer)
    width_pt: Mapped[float] = mapped_column(Float)
    height_pt: Mapped[float] = mapped_column(Float)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped["Document"] = relationship(back_populates="pages")


class OcrLine(Base):
    """bbox는 [x0,y0,x1,y1] 페이지 폭/높이 기준 0~1 정규화 좌표 (프론트 좌표계와 동일 소스)."""

    __tablename__ = "ocr_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    page_no: Mapped[int] = mapped_column(Integer)
    line_id: Mapped[str] = mapped_column(String)  # 예: "L1-2" (페이지 내 순번 기반, 프론트/하이라이트가 참조)
    text: Mapped[str] = mapped_column(String)
    bbox: Mapped[list] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String)  # pdf_text / paddle / tesseract 등 OCR·추출 엔진
    table_cell: Mapped[str | None] = mapped_column(String, nullable=True)  # 예: "r1,c1"

    document: Mapped["Document"] = relationship(back_populates="ocr_lines")
