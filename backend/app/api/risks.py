import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.risk import PatchRiskRequest, RerunResponse, RiskFinding, RisksResponse

router = APIRouter(tags=["risks"])


@router.get("/documents/{document_id}/risks", response_model=RisksResponse)
async def get_risks(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): DISMISSED 제외 summary 집계")


@router.post("/documents/{document_id}/risks/rerun", response_model=RerunResponse, status_code=202)
async def rerun_risks(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 위험조항 재탐지 job 생성")


@router.patch("/risks/{risk_id}", response_model=RiskFinding)
async def patch_risk(risk_id: uuid.UUID, payload: PatchRiskRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): status/note 갱신")
