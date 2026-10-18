from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.session import Base


class LlmCache(Base):
    """03_데이터정의 §5.19: LLM response cache. prompt_hash = ai.llm.prompt_hash(model, prompt_version, prompt)."""

    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
