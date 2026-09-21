import uuid
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile

from app.schemas.common import Paginated
from app.schemas.document import (
    DocumentDetail,
    DocumentListItem,
    DocumentStatusResponse,
    LinesResponse,
    ReprocessRequest,
    ReprocessResponse,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=Paginated[DocumentListItem])
async def list_documents(
    q: str | None = None,
    status: str | None = None,  # 콤마로 구분된 DocumentStatus 목록 (예: "OCR,EXTRACTING")
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    page: int = 1,
    size: int = 20,
):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 검색/상태 필터 + 페이지네이션 조회")


@router.post("", response_model=UploadResponse, status_code=202)
async def upload_documents(
    files: list[UploadFile] = File(...),
    ocr_engine: Literal["auto", "paddle", "tesseract"] = Form("auto"),
    skip_risk: bool = Form(False),
):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 파일 저장 + documents/jobs 레코드 생성 + 파이프라인 트리거")


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): jobs 테이블 조회")


@router.get("/{document_id}/pdf")
async def get_document_pdf(document_id: uuid.UUID) -> Response:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 정규화된 PDF 바이너리 스트리밍")


@router.get("/{document_id}/export/pdf")
async def export_document_pdf(document_id: uuid.UUID) -> Response:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 하이라이트가 합성된 PDF 생성/스트리밍")


@router.get("/{document_id}/lines", response_model=LinesResponse)
async def get_document_lines(document_id: uuid.UUID, page: int = Query(...)):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): ocr_lines 페이지별 조회")


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.post("/{document_id}/reprocess", response_model=ReprocessResponse, status_code=202)
async def reprocess_document(document_id: uuid.UUID, payload: ReprocessRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): from_step부터 파이프라인 재실행 job 생성")


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")
