import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.session import Base


class ChatSession(Base):
    """regulation_ids: 이 세션에서 검색 대상으로 스코프를 좁힐 규정 id 목록(빈 배열이면 전체 규정 대상)."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    regulation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session")


class ChatMessage(Base):
    """role: user|assistant. answer_status(assistant만): ANSWERED|NOT_FOUND|ERROR.
    suggestions: Suggestion[] 구조 그대로 JSON 저장(프론트 타입과 1:1, NOT_FOUND일 때만 채움).
    citations/feedback은 03_API_명세서 설계대로 별도 테이블(citations/message_feedback)로 분리했다
    (환각 평가·피드백 집계를 SQL로 바로 할 수 있게, 그리고 regulation_chunks가 재색인으로 없어져도
    과거 인용 기록 자체는 남도록 — 그래서 chunk_id/regulation_id/node_id는 하드 FK를 걸지 않는다)."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    answer_status: Mapped[str | None] = mapped_column(String, nullable=True)
    suggestions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(back_populates="message", cascade="all, delete-orphan", order_by="Citation.ref")
    feedback: Mapped["MessageFeedback | None"] = relationship(back_populates="message", cascade="all, delete-orphan", uselist=False)


class Citation(Base):
    """근거 조항 인용 1건. quoted_span으로 환각(hallucination) 평가에 쓴다(citations 테이블 — 03_API_명세서).
    chunk_id/regulation_id/node_id는 재색인·아카이브로 원본이 사라져도 인용 이력은 남아야 해서
    하드 FK를 걸지 않는다(참조만 하는 느슨한 UUID)."""

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"))
    ref: Mapped[int] = mapped_column(Integer)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    regulation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    regulation_title: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    quoted_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    message: Mapped["ChatMessage"] = relationship(back_populates="citations")


class MessageFeedback(Base):
    """메시지당 최신 피드백 1건(재전송 시 덮어씀). rating: 1(도움됨) | -1(도움안됨)."""

    __tablename__ = "message_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), unique=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped["ChatMessage"] = relationship(back_populates="feedback")
