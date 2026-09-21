import uuid

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    regulation_ids: list[uuid.UUID] = []
    top_k: int = 5


class SearchResultItem(BaseModel):
    """디버그용 하이브리드 검색 결과 — 단계별 점수를 그대로 노출해 검색 파이프라인을 검증한다."""

    chunk_id: uuid.UUID
    regulation_title: str
    path: str
    content: str
    bm25_score: float
    vector_score: float
    rrf_score: float
    rerank_score: float


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    latency_ms: int
