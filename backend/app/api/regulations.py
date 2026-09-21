import uuid
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from app.schemas.regulation import (
    ReindexRequest,
    ReindexResponse,
    RegNodeContent,
    RegulationDetail,
    RegulationListItem,
    UploadRegulationResponse,
)

router = APIRouter(prefix="/regulations", tags=["regulations"])


@router.get("")
async def list_regulations() -> dict[str, list[RegulationListItem]]:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.post("", response_model=UploadRegulationResponse, status_code=202)
async def upload_regulation(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: Literal["정관", "규정", "지침", "매뉴얼"] = Form(...),
    effective_date: str | None = Form(None),
):
    raise HTTPException(
        status_code=501,
        detail="구현 대기 (6주차): 동일 title 기존 버전 ARCHIVED 처리 + 구조분석/청킹/인덱싱 job 생성",
    )


@router.get("/{regulation_id}/pdf")
async def get_regulation_pdf(regulation_id: uuid.UUID) -> Response:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 근거 팝업용 PDF 바이너리 스트리밍")


@router.get("/{regulation_id}/nodes/{node_id}", response_model=RegNodeContent)
async def get_regulation_node(regulation_id: uuid.UUID, node_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/{regulation_id}", response_model=RegulationDetail)
async def get_regulation(regulation_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): status=INDEXED일 때만 tree 채움")


@router.post("/{regulation_id}/reindex", response_model=ReindexResponse, status_code=202)
async def reindex_regulation(regulation_id: uuid.UUID, payload: ReindexRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.delete("/{regulation_id}", status_code=204)
async def delete_regulation(regulation_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): status=ARCHIVED로 소프트 삭제")
