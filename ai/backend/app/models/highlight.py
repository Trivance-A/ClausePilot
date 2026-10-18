import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Highlight(Base):
    """extraction_field_id 또는 risk_finding_id 중 정확히 하나만 채워진다 (필드 근거 하이라이트 vs 위험조항 근거 하이라이트).
    origin: auto(AI 생성) | manual(사용자가 직접 지정/수정). bbox는 [x0,y0,x1,y1] 0~1 정규화 좌표.
    document_id는 조회 편의를 위한 비정규화 컬럼(생성 시 부모와 동일 문서로 고정)."""

    __tablename__ = "highlights"
    __table_args__ = (
        CheckConstraint(
            "(extraction_field_id IS NOT NULL) != (risk_finding_id IS NOT NULL)",
            name="ck_highlight_exactly_one_parent",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    extraction_field_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extraction_fields.id", ondelete="CASCADE"), nullable=True)
    risk_finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_findings.id", ondelete="CASCADE"), nullable=True)
    page_no: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(String, default="auto")
    ocr_line_id: Mapped[str | None] = mapped_column(String, nullable=True)  # OcrLine.line_id 참조(페이지 범위 내 식별자, 느슨한 참조)

    extraction_field: Mapped["ExtractionField | None"] = relationship(back_populates="highlights")
    risk_finding: Mapped["RiskFinding | None"] = relationship(back_populates="highlights")
