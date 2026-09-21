import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.eval import EvalRun as EvalRunModel
from app.models.user import User
from app.schemas.eval import EvalRun, RunEvalRequest, RunEvalResponse
from app.services.eval_metrics import compute_metrics

router = APIRouter(prefix="/eval", tags=["eval"])


def _to_out(run: EvalRunModel) -> EvalRun:
    return EvalRun(id=run.id, suite=run.suite, status=run.status, started_at=run.started_at, finished_at=run.finished_at, metrics=run.metrics, failures=run.failures)


@router.post("/run", response_model=RunEvalResponse, status_code=202)
async def run_eval(payload: RunEvalRequest, db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    now = datetime.now(timezone.utc)
    metrics = compute_metrics(db, payload.suite)
    run = EvalRunModel(suite=payload.suite, status="DONE", started_at=now, finished_at=datetime.now(timezone.utc), metrics=metrics or None, failures=[])
    db.add(run)
    db.commit()
    return RunEvalResponse(run_id=run.id)


@router.get("/runs/{run_id}", response_model=EvalRun)
async def get_eval_run(run_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    run = db.get(EvalRunModel, run_id)
    if not run:
        raise ApiError(404, "NOT_FOUND", "평가 실행 기록을 찾을 수 없습니다")
    return _to_out(run)


@router.get("/runs")
async def list_eval_runs(db: Session = Depends(get_db), _user: User = Depends(require_admin)) -> dict[str, list[EvalRun]]:
    runs = db.query(EvalRunModel).order_by(EvalRunModel.started_at.desc().nullslast()).all()
    return {"items": [_to_out(r) for r in runs]}
