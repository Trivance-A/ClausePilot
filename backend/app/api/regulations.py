import uuid

from fastapi import APIRouter, HTTPException, UploadFile

router = APIRouter(prefix="/regulations", tags=["regulations"])


@router.post("", status_code=202)
async def upload_regulation(file: UploadFile):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 규정 문서 업로드 + 구조분석/청킹/인덱싱 트리거")


@router.get("/{regulation_id}/status")
async def get_regulation_status(regulation_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")
