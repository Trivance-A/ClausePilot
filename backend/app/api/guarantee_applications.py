import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/guarantee-applications", tags=["guarantee-applications"])


class AutoFillIn(BaseModel):
    document_id: uuid.UUID


class AutoFillOut(BaseModel):
    application_id: uuid.UUID
    filled_fields: dict


@router.post("/auto-fill", response_model=AutoFillOut)
async def auto_fill(payload: AutoFillIn):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): extracted_fields → 보증신청 Demo 필드 매핑")
