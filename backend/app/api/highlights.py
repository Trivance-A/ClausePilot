import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.extraction import CreateHighlightBody, Highlight, PatchHighlightRequest

router = APIRouter(tags=["highlights"])


@router.post("/documents/{document_id}/highlights", response_model=Highlight, status_code=201)
async def create_highlight(document_id: uuid.UUID, payload: CreateHighlightBody):
    raise HTTPException(
        status_code=501,
        detail="구현 대기 (6주차): field_code/risk_finding_id 중 정확히 하나 검증 후 수동 하이라이트 생성",
    )


@router.patch("/highlights/{highlight_id}", response_model=Highlight)
async def patch_highlight(highlight_id: uuid.UUID, payload: PatchHighlightRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): bbox 수정 + origin=manual 전환")


@router.delete("/highlights/{highlight_id}", status_code=204)
async def delete_highlight(highlight_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")
