import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.extraction import ExtractionField, ExtractionResponse, FieldCode, FieldPatch

router = APIRouter(prefix="/documents/{document_id}/extractions", tags=["extractions"])


@router.get("", response_model=ExtractionResponse)
async def get_extractions(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.patch("/fields/{field_code}", response_model=ExtractionField)
async def patch_extraction_field(document_id: uuid.UUID, field_code: FieldCode, payload: FieldPatch):
    raise HTTPException(
        status_code=501,
        detail="구현 대기 (6주차): 필드 수정 반영 + extraction.status 재계산(AUTO/REVIEWED/CONFIRMED)",
    )
