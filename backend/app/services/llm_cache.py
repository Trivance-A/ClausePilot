"""DB-backed LLM response cache (03_데이터정의 §5.19 llm_cache) handed to ai.llm.LLMClient(cache=...)."""

from collections.abc import Iterator, MutableMapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ai.llm import env_model
from app.db.session import SessionLocal
from app.models.llm_cache import LlmCache


class DbLlmCache(MutableMapping[str, Any]):
    """Each access opens its own short session: the risk engine calls the LLM from worker threads and must not share the
    pipeline's session, and a cached response survives a pipeline that fails later."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or env_model()

    def __getitem__(self, key: str) -> Any:
        with SessionLocal() as db:
            row = db.get(LlmCache, key)
        if row is None:
            raise KeyError(key)
        return row.response

    def __setitem__(self, key: str, value: Any) -> None:
        with SessionLocal() as db:
            # parallel LLM rules may store the same prompt at once
            db.execute(insert(LlmCache).values(prompt_hash=key, model_name=self.model_name, response=value).on_conflict_do_nothing())
            db.commit()

    def __delitem__(self, key: str) -> None:
        with SessionLocal() as db:
            if db.query(LlmCache).filter(LlmCache.prompt_hash == key).delete() == 0:
                raise KeyError(key)
            db.commit()

    def __iter__(self) -> Iterator[str]:
        with SessionLocal() as db:
            return iter(db.scalars(select(LlmCache.prompt_hash)).all())

    def __len__(self) -> int:
        with SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(LlmCache)) or 0
