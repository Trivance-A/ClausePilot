"""실제 Postgres 없이도 ORM 모델/관계 설정 오류(FK 오타, 순환참조 등)를 잡기 위한 정적 검증.
DDL을 실제로 실행하지는 않는다 (JSONB 등 Postgres 전용 타입은 실 DB에서만 검증 가능)."""

from sqlalchemy.orm import configure_mappers

from app.db.session import Base
from app.models import chat, document, regulation  # noqa: F401 (모델 등록을 위해 import)

EXPECTED_TABLES = {
    "documents",
    "ocr_blocks",
    "extracted_fields",
    "risk_flags",
    "guarantee_applications",
    "regulations",
    "regulation_chunks",
    "chat_sessions",
    "chat_messages",
}


def test_all_expected_tables_are_registered():
    assert EXPECTED_TABLES.issubset(Base.metadata.tables.keys())


def test_mappers_configure_without_error():
    configure_mappers()
