import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.colors import FIELD_COLOR_MAP
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.extraction import Extraction, ExtractionField
from app.models.highlight import Highlight
from app.models.user import User
from app.schemas.extraction import ExtractionField as ExtractionFieldOut
from app.schemas.extraction import ExtractionResponse, FieldCode, FieldPatch
from app.schemas.extraction import Highlight as HighlightOut

router = APIRouter(prefix="/documents/{document_id}/extractions", tags=["extractions"])


def _to_highlight_out(h: Highlight) -> HighlightOut:
    return HighlightOut(id=h.id, page_no=h.page_no, bbox=tuple(h.bbox), origin=h.origin, ocr_line_id=h.ocr_line_id)


def _to_field_out(f: ExtractionField) -> ExtractionFieldOut:
    return ExtractionFieldOut(
        field_code=f.field_code,
        label=f.label,
        color_key=f.color_key,
        raw_value=f.raw_value,
        normalized_value=f.normalized_value,
        confidence=f.confidence,
        mapping_method=f.mapping_method,
        is_confirmed=f.is_confirmed,
        reviewer_note=f.reviewer_note,
        highlights=[_to_highlight_out(h) for h in f.highlights],
    )


def _get_extraction_or_404(db: Session, document_id: uuid.UUID) -> Extraction:
    extraction = db.query(Extraction).filter(Extraction.document_id == document_id).one_or_none()
    if not extraction:
        raise ApiError(404, "NOT_FOUND", "추출 결과가 없습니다 (아직 분석 중이거나 실패했을 수 있습니다)")
    return extraction


@router.get("", response_model=ExtractionResponse)
async def get_extractions(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    extraction = _get_extraction_or_404(db, document_id)
    return ExtractionResponse(
        extraction_id=extraction.id,
        status=extraction.status,
        fields=[_to_field_out(f) for f in extraction.fields],
        color_map=FIELD_COLOR_MAP,
    )


@router.patch("/fields/{field_code}", response_model=ExtractionFieldOut)
async def patch_extraction_field(
    document_id: uuid.UUID, field_code: FieldCode, payload: FieldPatch, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    extraction = _get_extraction_or_404(db, document_id)
    field = next((f for f in extraction.fields if f.field_code == field_code), None)
    if not field:
        raise ApiError(404, "NOT_FOUND", "필드를 찾을 수 없습니다")

    if payload.raw_value is not None:
        field.raw_value = payload.raw_value
        if field.mapping_method == "none":
            field.mapping_method = "manual"
        field.confidence = 1.0
    if payload.normalized_value is not None:
        field.normalized_value = payload.normalized_value
    if payload.is_confirmed is not None:
        field.is_confirmed = payload.is_confirmed
    if payload.reviewer_note is not None:
        field.reviewer_note = payload.reviewer_note

    extraction.status = "CONFIRMED" if all(f.is_confirmed for f in extraction.fields) else "REVIEWED"
    db.commit()
    db.refresh(field)
    return _to_field_out(field)
