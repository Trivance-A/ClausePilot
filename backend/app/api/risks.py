import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.document import Document, OcrLine
from app.models.extraction import Extraction
from app.models.job import Job
from app.models.risk import RiskFinding
from app.models.user import User
from app.schemas.extraction import Highlight as HighlightOut
from app.schemas.risk import PatchRiskRequest, RerunResponse
from app.schemas.risk import RiskFinding as RiskFindingOut
from app.schemas.risk import RisksResponse
from app.services.pipeline import run_reprocess

router = APIRouter(tags=["risks"])


def _to_out(r: RiskFinding) -> RiskFindingOut:
    return RiskFindingOut(
        id=r.id,
        category=r.category,
        severity=r.severity,
        score=r.score,
        rule_code=r.rule_code,
        title=r.title,
        description=r.description,
        evidence_text=r.evidence_text,
        highlights=[HighlightOut(id=h.id, page_no=h.page_no, bbox=tuple(h.bbox), origin=h.origin, ocr_line_id=h.ocr_line_id) for h in r.highlights],
        llm_reasoning=r.llm_reasoning,
        status=r.status,
        note=r.note,
    )


@router.get("/documents/{document_id}/risks", response_model=RisksResponse)
async def get_risks(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    risks = db.query(RiskFinding).filter(RiskFinding.document_id == document_id).all()
    summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in risks:
        if r.status != "DISMISSED":
            summary[r.severity] += 1
    return RisksResponse(items=[_to_out(r) for r in risks], summary=summary)


@router.post("/documents/{document_id}/risks/rerun", response_model=RerunResponse, status_code=202)
async def rerun_risks(document_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    document = db.get(Document, document_id)
    if not document:
        raise ApiError(404, "NOT_FOUND", "문서를 찾을 수 없습니다")
    if not db.query(OcrLine).filter(OcrLine.document_id == document_id).first() or not db.query(Extraction).filter(Extraction.document_id == document_id).first():
        raise ApiError(409, "INVALID_STATE", "분석이 완료되지 않아 위험조항을 재탐지할 수 없습니다")

    job = Job(job_type="process_document", target_id=document_id, target_name=document.original_name, status="QUEUED")
    db.add(job)
    db.commit()
    background_tasks.add_task(run_reprocess, document_id, job.id, "risk")
    return RerunResponse(job_id=job.id)


@router.patch("/risks/{risk_id}", response_model=RiskFindingOut)
async def patch_risk(risk_id: uuid.UUID, payload: PatchRiskRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    risk = db.get(RiskFinding, risk_id)
    if not risk:
        raise ApiError(404, "NOT_FOUND", "위험조항을 찾을 수 없습니다")
    risk.status = payload.status
    risk.note = payload.note
    db.commit()
    db.refresh(risk)
    return _to_out(risk)
