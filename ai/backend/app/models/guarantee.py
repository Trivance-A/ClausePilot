import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.session import Base


class GuaranteeApplication(Base):
    """guarantee_type: contract|bid|defect|payment|advance|other. status: DRAFT|SUBMITTED.
    form_values: GuaranteeFormValues 스냅샷(수정 가능). field_sources: 각 필드가 어떤 추출 필드/하이라이트에서 왔는지
    {field_code: {field_id, confidence, highlight_ids, page_no}}. required_fields: guarantee_type별 필수 필드 목록(FIELD_CODES 부분집합).
    viewer_url은 저장하지 않고 응답 시 document_id 기반으로 생성한다."""

    __tablename__ = "guarantee_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    guarantee_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="DRAFT")
    form_values: Mapped[dict] = mapped_column(JSONB)
    field_sources: Mapped[dict] = mapped_column(JSONB, default=dict)
    required_fields: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
