from fastapi import APIRouter, HTTPException

from app.schemas.search import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def debug_search(payload: SearchRequest):
    raise HTTPException(
        status_code=501,
        detail="구현 대기 (6주차, 디버그용): BM25+Vector 검색 → RRF 결합 → rerank 단계별 점수 노출",
    )
