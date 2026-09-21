import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.eval import EvalRun, RunEvalRequest, RunEvalResponse

router = APIRouter(prefix="/eval", tags=["eval"])


@router.post("/run", response_model=RunEvalResponse, status_code=202)
async def run_eval(payload: RunEvalRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 평가 suite 실행 job 생성")


@router.get("/runs/{run_id}", response_model=EvalRun)
async def get_eval_run(run_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/runs")
async def list_eval_runs() -> dict[str, list[EvalRun]]:
    """명세에 없어 프론트가 가정한 보조 엔드포인트 (front 폴더/README.md 참고) — 없으면 빈 목록으로 응답해도 무방."""
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")
