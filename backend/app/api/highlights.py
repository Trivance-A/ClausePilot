import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.document import OcrLine
from app.models.extraction import Extraction, ExtractionField
from app.models.highlight import Highlight
from app.models.risk import RiskFinding
from app.models.user import User
from app.schemas.extraction import CreateHighlightBody, Highlight as HighlightOut, PatchHighlightRequest

router = APIRouter(tags=["highlights"])


def _to_out(h: Highlight) -> HighlightOut:
    return HighlightOut(id=h.id, page_no=h.page_no, bbox=tuple(h.bbox), origin=h.origin, ocr_line_id=h.ocr_line_id)


@router.post("/documents/{document_id}/highlights", response_model=HighlightOut, status_code=201)
async def create_highlight(document_id: uuid.UUID, payload: CreateHighlightBody, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if (payload.field_code is None) == (payload.risk_finding_id is None):
        raise ApiError(400, "VALIDATION_ERROR", "field_code 또는 risk_finding_id 중 정확히 하나가 필요합니다")

    highlight = Highlight(document_id=document_id, page_no=payload.page_no, bbox=list(payload.bbox), origin="manual")

    if payload.field_code:
        extraction = db.query(Extraction).filter(Extraction.document_id == document_id).one_or_none()
        field = next((f for f in extraction.fields if f.field_code == payload.field_code), None) if extraction else None
        if not field:
            raise ApiError(404, "NOT_FOUND", "필드를 찾을 수 없습니다")
        highlight.extraction_field_id = field.id
        if not field.raw_value:
            candidate = (
                db.query(OcrLine)
                .filter(OcrLine.document_id == document_id, OcrLine.page_no == payload.page_no)
                .all()
            )
            match = next((line for line in candidate if abs(line.bbox[1] - payload.bbox[1]) < 0.02), None)
            if match:
                field.raw_value = match.text
                field.normalized_value = {"text": match.text}
                field.confidence = 1.0
        field.mapping_method = "manual"
    else:
        risk = db.query(RiskFinding).filter(RiskFinding.id == payload.risk_finding_id, RiskFinding.document_id == document_id).one_or_none()
        if not risk:
            raise ApiError(404, "NOT_FOUND", "위험조항을 찾을 수 없습니다")
        highlight.risk_finding_id = risk.id

    db.add(highlight)
    db.commit()
    db.refresh(highlight)
    return _to_out(highlight)


@router.patch("/highlights/{highlight_id}", response_model=HighlightOut)
async def patch_highlight(highlight_id: uuid.UUID, payload: PatchHighlightRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    highlight = db.get(Highlight, highlight_id)
    if not highlight:
        raise ApiError(404, "NOT_FOUND", "하이라이트를 찾을 수 없습니다")
    highlight.bbox = list(payload.bbox)
    if payload.page_no is not None:
        highlight.page_no = payload.page_no
    highlight.origin = "manual"
    if highlight.extraction_field:
        highlight.extraction_field.mapping_method = "manual"
    db.commit()
    db.refresh(highlight)
    return _to_out(highlight)


@router.delete("/highlights/{highlight_id}", status_code=204)
async def delete_highlight(highlight_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    highlight = db.get(Highlight, highlight_id)
    if not highlight:
        raise ApiError(404, "NOT_FOUND", "하이라이트를 찾을 수 없습니다")
    db.delete(highlight)
    db.commit()
