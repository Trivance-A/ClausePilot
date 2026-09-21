from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas.admin import AdminJob, AdminStats, ChatLogItem, JobStatus
from app.schemas.common import Paginated

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats():
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/jobs")
async def list_admin_jobs(status: JobStatus | None = None) -> dict[str, list[AdminJob]]:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/logs/chat", response_model=None)
async def list_chat_logs(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    answer_status: str | None = None,
    page: int = 1,
    size: int = 20,
    format: str | None = None,  # "csv"면 text/csv 다운로드
) -> Paginated[ChatLogItem] | Response:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): format=csv 일 때 CSV 스트리밍")
