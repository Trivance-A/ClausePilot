import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.session import Base


class Regulation(Base):
    """doc_type: 정관|규정|지침|매뉴얼. status: UPLOADED|PARSING|INDEXED|FAILED|ARCHIVED.
    같은 title로 재업로드하면 이전 버전은 ARCHIVED로 바뀌고 version이 +1 된다(재발행 이력 관리)."""

    __tablename__ = "regulations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String)
    doc_type: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="UPLOADED")
    source_pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    nodes: Mapped[list["RegulationNode"]] = relationship(back_populates="regulation")
    chunks: Mapped[list["RegulationChunk"]] = relationship(back_populates="regulation")


class RegulationNode(Base):
    """장·조·항·목 트리 구조. level: chapter|section|article|paragraph|item|subitem|appendix.
    parent_id로 자기참조 트리를 구성하고, sort_order로 형제 노드 순서를 유지한다.
    path는 'GET /regulations/{id}/nodes/{nodeId}' 등에서 그대로 노출하는 표시용 경로(예: 제3장>제12조(계약보증금)>제2항)."""

    __tablename__ = "regulation_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    regulation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regulations.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regulation_nodes.id"), nullable=True)
    level: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    path: Mapped[str] = mapped_column(String)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    regulation: Mapped["Regulation"] = relationship(back_populates="nodes")
    chunks: Mapped[list["RegulationChunk"]] = relationship(back_populates="node")


class RegulationChunk(Base):
    """RAG 검색 대상 단위. embedding_ref는 Vector DB(Chroma/FAISS) 쪽 인덱스 참조 ID."""

    __tablename__ = "regulation_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    regulation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regulations.id", ondelete="CASCADE"))
    node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regulation_nodes.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    regulation: Mapped["Regulation"] = relationship(back_populates="chunks")
    node: Mapped["RegulationNode | None"] = relationship(back_populates="chunks")
