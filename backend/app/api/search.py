import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services.search import search as run_search

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def debug_search(payload: SearchRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    started = time.monotonic()
    results = run_search(db, payload.query, payload.regulation_ids or None, payload.top_k)
    latency_ms = int((time.monotonic() - started) * 1000)
    return SearchResponse(
        results=[
            SearchResultItem(
                chunk_id=r["chunk_id"], regulation_title=r["regulation_title"], path=r["path"], content=r["content"],
                bm25_score=r["bm25_score"], vector_score=r["vector_score"], rrf_score=r["rrf_score"], rerank_score=r["rerank_score"],
            )
            for r in results
        ],
        latency_ms=latency_ms,
    )
