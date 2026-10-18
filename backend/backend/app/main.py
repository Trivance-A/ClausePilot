from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api import admin, auth, chat, documents, eval, extractions, guarantee, highlights, regulations, risks, search
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.seed import ensure_default_risk_rules, ensure_demo_users
from app.db.session import Base, engine

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))  # regulation_chunks.embedding(pgvector) 컬럼용
    Base.metadata.create_all(bind=engine)  # 개발 편의용 부트스트랩. 실제 배포는 Alembic 마이그레이션 사용
    if settings.seed_demo_users:
        ensure_demo_users()
    ensure_default_risk_rules()
    yield


app = FastAPI(title="ClausePilot API", lifespan=lifespan)
register_exception_handlers(app)

for router in (
    auth.router,
    documents.router,
    extractions.router,
    highlights.router,
    risks.router,
    guarantee.router,
    regulations.router,
    search.router,
    chat.router,
    admin.router,
    eval.router,
):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/health")
def health_check():
    return {"status": "ok"}
