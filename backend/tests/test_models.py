"""실제 Postgres 없이도 ORM 모델/관계 설정 오류(FK 오타, 순환참조 등)를 잡기 위한 정적 검증.
DDL을 실제로 실행하지는 않는다 (JSONB 등 Postgres 전용 타입은 실 DB에서만 검증 가능)."""

from sqlalchemy.orm import configure_mappers

from app.db.session import Base
from app.models import (  # noqa: F401 (모델 등록을 위해 import)
    chat,
    document,
    eval,
    extraction,
    guarantee,
    highlight,
    job,
    regulation,
    risk,
    risk_rule,
    user,
)

EXPECTED_TABLES = {
    "users",
    "documents",
    "pages",
    "ocr_lines",
    "extractions",
    "extraction_fields",
    "highlights",
    "risk_findings",
    "risk_rules",
    "guarantee_applications",
    "regulations",
    "regulation_nodes",
    "regulation_chunks",
    "chat_sessions",
    "chat_messages",
    "citations",
    "message_feedback",
    "jobs",
    "eval_runs",
}


def test_all_expected_tables_are_registered():
    assert EXPECTED_TABLES.issubset(Base.metadata.tables.keys())


def test_mappers_configure_without_error():
    configure_mappers()


def test_pipeline_module_alone_registers_all_models_for_mapper_configuration():
    """RQ worker 프로세스는 app.services.pipeline만 임포트한다(다른 라우터/main.py를 거치지 않음).
    한 번 실제로 걸렸던 버그: pipeline.py가 직접 참조하지 않는 모델(User 등)이 Base.metadata에
    등록되지 않아, users FK를 가진 Document 저장 시 NoReferencedTableError가 났다. 같은 pytest
    프로세스 안에서는 다른 테스트가 이미 전체 모델을 임포트해놨을 수 있어 이 버그가 안 보이므로,
    반드시 별도 서브프로세스에서 pipeline만 단독 임포트해 검증해야 한다."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import app.services.pipeline; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('OK')"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0 and "OK" in result.stdout, f"stdout={result.stdout}\nstderr={result.stderr}"
