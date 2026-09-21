import uuid

from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas.document import DocumentResultOut, DocumentStatusOut, DocumentUploadOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadOut, status_code=202)
async def upload_document(file: UploadFile):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 파일 저장 + AI 파이프라인 트리거")


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
async def get_document_status(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/{document_id}/result", response_model=DocumentResultOut)
async def get_document_result(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/{document_id}/ocr-blocks")
async def get_document_ocr_blocks(document_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="구현 대기 (QA/디버깅용, 6주차 이후)")
