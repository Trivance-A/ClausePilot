import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.guarantee import CreateGuaranteeRequest, GuaranteeApplication, PatchGuaranteeRequest

router = APIRouter(prefix="/guarantee-applications", tags=["guarantee-applications"])


@router.post("", response_model=GuaranteeApplication, status_code=201)
async def create_guarantee_application(payload: CreateGuaranteeRequest):
    raise HTTPException(
        status_code=501,
        detail="구현 대기 (6주차): extracted_fields → form_values/field_sources 매핑, "
        "분석 미완료 시 409 INVALID_STATE",
    )


@router.get("/{application_id}", response_model=GuaranteeApplication)
async def get_guarantee_application(application_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.patch("/{application_id}", response_model=GuaranteeApplication)
async def patch_guarantee_application(application_id: uuid.UUID, payload: PatchGuaranteeRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 사용자 수정한 form_values 저장")
