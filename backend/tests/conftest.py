"""통합 테스트 하네스. 실제 Postgres+Redis가 필요하다 (docker compose up -d db redis, README 참고).
DATABASE_URL/REDIS_URL을 다른 값으로 주지 않으면 docker-compose가 노출하는 기본 포트를 쓴다."""

import os
import tempfile

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5433/contract_ai")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="clausepilot_test_storage_"))
os.environ["SEED_DEMO_USERS"] = "true"
os.environ["QUEUE_ASYNC"] = "false"  # 워커 프로세스 없이 enqueue() 호출 시 즉시 동기 실행(RQ 공식 테스트 모드)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import settings
from app.db.session import Base
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _reset_database():
    engine = create_engine(settings.database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_headers(client) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def user_headers(client) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "user1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
