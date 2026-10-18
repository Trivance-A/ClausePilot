import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class RiskFinding(Base):
    """category: penalty | missing | contradiction | toxic | policy
    severity: HIGH | MEDIUM | LOW (문서의 risk_summary는 조회 시 DISMISSED를 제외하고 집계)
    status: OPEN | ACKNOWLEDGED | DISMISSED
    llm_reasoning은 LLM이 위험으로 판단한 근거(조항/사유/기준 등)를 자유 형식 JSON으로 보관."""

    __tablename__ = "risk_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float)
    rule_code: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_reasoning: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="OPEN")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    highlights: Mapped[list["Highlight"]] = relationship(back_populates="risk_finding")
