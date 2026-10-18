import uuid
from datetime import date, datetime, time
from typing import Literal

import pymupdf as fitz
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, Response

from app.core.colors import FIELD_COLOR_MAP, RISK_SEVERITY_COLOR, hex_to_rgb01
from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.queue import default_queue
from app.core.storage import save_upload, uploads_dir
from app.db.session import get_db
from app.models.document import Document, OcrLine, Page
from app.models.extraction import Extraction
from app.models.highlight import Highlight
from app.models.job import Job
from app.models.risk import RiskFinding
from app.models.user import User
from app.schemas.common import Paginated
from app.schemas.document import (
    DocumentDetail,
    DocumentListItem,
    DocumentStatusResponse,
    ExtractionRef,
    Job as JobSchema,
    LinesResponse,
    OcrLineOut,
    PageMeta,
    ReprocessRequest,
    ReprocessResponse,
    UploadItem,
    UploadResponse,
)
from app.services.pipeline import run_document_pipeline, run_reprocess

router = APIRouter(prefix="/documents", tags=["documents"])

IN_PROGRESS = {"UPLOADED", "NORMALIZING", "OCR", "EXTRACTING", "RISK"}


def _risk_summaries(db: Session, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int] | None]:
    if not document_ids:
        return {}
    rows = (
        db.query(RiskFinding.document_id, RiskFinding.severity, func.count())
        .filter(RiskFinding.document_id.in_(document_ids), RiskFinding.status != "DISMISSED")
        .group_by(RiskFinding.document_id, RiskFinding.severity)
        .all()
    )
    any_finding = {
        doc_id
        for (doc_id,) in db.query(RiskFinding.document_id).filter(RiskFinding.document_id.in_(document_ids)).distinct()
    }
    summaries: dict[uuid.UUID, dict[str, int] | None] = {
        doc_id: ({"HIGH": 0, "MEDIUM": 0, "LOW": 0} if doc_id in any_finding else None) for doc_id in document_ids
    }
    for doc_id, severity, count in rows:
        if summaries[doc_id] is not None:
            summaries[doc_id][severity] = count
    return summaries


def _to_list_item(document: Document, risk_summary: dict[str, int] | None) -> DocumentListItem:
    return DocumentListItem(
        id=document.id,
        original_name=document.original_name,
        original_format=document.original_format,
        source_type=document.source_type,
        page_count=document.page_count,
        status=document.status,
        risk_summary=risk_summary,
        created_at=document.created_at,
    )


def _parse_date_bound(value: str | None, *, end_of_day: bool) -> datetime | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return datetime.combine(d, time.max if end_of_day else time.min)


@router.get("", response_model=Paginated[DocumentListItem])
async def list_documents(
    q: str | None = None,
    status: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Document)
    if q:
        query = query.filter(Document.original_name.ilike(f"%{q}%"))
    if status:
        query = query.filter(Document.status.in_([s.strip() for s in status.split(",") if s.strip()]))
    if start := _parse_date_bound(from_, end_of_day=False):
        query = query.filter(Document.created_at >= start)
    if end := _parse_date_bound(to, end_of_day=True):
        query = query.filter(Document.created_at <= end)

    total = query.count()
    documents = query.order_by(Document.created_at.desc()).offset((page - 1) * size).limit(size).all()
    summaries = _risk_summaries(db, [d.id for d in documents])
    items = [_to_list_item(d, summaries[d.id]) for d in documents]
    return Paginated(items=items, total=total, page=page, size=size)


@router.post("", response_model=UploadResponse, status_code=202)
async def upload_documents(
    files: list[UploadFile] = File(...),
    ocr_engine: Literal["auto", "paddle", "tesseract"] = Form("auto"),
    skip_risk: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items: list[UploadItem] = []
    for file in files:
        doc_id = uuid.uuid4()
        content = await file.read()
        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "pdf"
        path = save_upload(uploads_dir(), doc_id, file.filename or f"{doc_id}.{ext}", content)

        document = Document(id=doc_id, owner_id=user.id, original_name=file.filename or str(doc_id), original_format=ext, original_path=path, status="UPLOADED")
        db.add(document)
        job = Job(job_type="process_document", target_id=doc_id, target_name=document.original_name, status="QUEUED")
        db.add(job)
        db.commit()

        default_queue.enqueue(run_document_pipeline, doc_id, job.id)
        items.append(UploadItem(document_id=doc_id, job_id=job.id, original_name=document.original_name, status="UPLOADED"))

    return UploadResponse(items=items)


def _get_document_or_404(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise ApiError(404, "NOT_FOUND", "문서를 찾을 수 없습니다")
    return document


def _latest_job(db: Session, document_id: uuid.UUID) -> Job | None:
    return (
        db.query(Job)
        .filter(Job.job_type == "process_document", Job.target_id == document_id)
        .order_by(Job.started_at.desc().nullslast())
        .first()
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    document = _get_document_or_404(db, document_id)
    job = _latest_job(db, document_id)
    job_out = JobSchema(id=job.id, current_step=job.current_step, progress=job.progress, error=job.error, status=job.status) if job else None
    return DocumentStatusResponse(status=document.status, job=job_out)


@router.get("/{document_id}/pdf")
async def get_document_pdf(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    document = _get_document_or_404(db, document_id)
    if not document.normalized_pdf_path:
        raise ApiError(409, "INVALID_STATE", "아직 정규화된 PDF가 없습니다")
    return FileResponse(document.normalized_pdf_path, media_type="application/pdf")


@router.get("/{document_id}/pages/{page_no}/image")
async def get_document_page_image(document_id: uuid.UUID, page_no: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """페이지를 200dpi PNG로 렌더링해 반환한다 (front 폴더의 pdf.js Viewer는 PDF를 직접 렌더링해 호출하지
    않지만, 명세서 03_API_명세서.docx에 정의되어 있어 구현 — 서버사이드 썸네일/미리보기 등에 쓸 수 있다)."""
    document = _get_document_or_404(db, document_id)
    if not document.normalized_pdf_path:
        raise ApiError(409, "INVALID_STATE", "아직 정규화된 PDF가 없습니다")

    doc = fitz.open(document.normalized_pdf_path)
    try:
        if page_no < 1 or page_no > doc.page_count:
            raise ApiError(404, "NOT_FOUND", "페이지를 찾을 수 없습니다")
        pixmap = doc[page_no - 1].get_pixmap(dpi=200)
        png_bytes = pixmap.tobytes("png")
    finally:
        doc.close()
    return Response(content=png_bytes, media_type="image/png")


@router.get("/{document_id}/export/pdf")
async def export_document_pdf(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    document = _get_document_or_404(db, document_id)
    if not document.normalized_pdf_path:
        raise ApiError(409, "INVALID_STATE", "아직 정규화된 PDF가 없습니다")

    highlights = db.query(Highlight).filter(Highlight.document_id == document_id).all()
    doc = fitz.open(document.normalized_pdf_path)
    try:
        for h in highlights:
            page = doc[h.page_no - 1]
            rect = fitz.Rect(
                h.bbox[0] * page.rect.width,
                h.bbox[1] * page.rect.height,
                h.bbox[2] * page.rect.width,
                h.bbox[3] * page.rect.height,
            )
            color_hex = RISK_SEVERITY_COLOR["HIGH"] if h.risk_finding_id else FIELD_COLOR_MAP.get(_field_color_key(h), "#FFEB3B")
            rgb = hex_to_rgb01(color_hex)
            page.draw_rect(rect, color=rgb, fill=rgb, fill_opacity=0.35, width=1)

        export_path = uploads_dir().parent / "exports" / f"{document_id}.pdf"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(export_path))
    finally:
        doc.close()
    return FileResponse(str(export_path), media_type="application/pdf", filename="highlight.pdf")


def _field_color_key(highlight: Highlight) -> str | None:
    if not highlight.extraction_field_id:
        return None
    field = highlight.extraction_field
    return field.color_key if field else None


@router.get("/{document_id}/lines", response_model=LinesResponse)
async def get_document_lines(document_id: uuid.UUID, page: int = Query(...), db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    _get_document_or_404(db, document_id)
    lines = db.query(OcrLine).filter(OcrLine.document_id == document_id, OcrLine.page_no == page).all()
    lines.sort(key=lambda line: (line.bbox[1], line.bbox[0]))
    return LinesResponse(
        page_no=page,
        lines=[OcrLineOut(id=line.id, line_id=line.line_id, text=line.text, bbox=tuple(line.bbox), confidence=line.confidence, source=line.source, table_cell=line.table_cell) for line in lines],
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    document = _get_document_or_404(db, document_id)
    pages = db.query(Page).filter(Page.document_id == document_id).order_by(Page.page_no).all()
    extraction = db.query(Extraction).filter(Extraction.document_id == document_id).one_or_none()
    summary = _risk_summaries(db, [document_id])[document_id]

    return DocumentDetail(
        **_to_list_item(document, summary).model_dump(),
        pages=[PageMeta(page_no=p.page_no, width_pt=p.width_pt, height_pt=p.height_pt, rotation=p.rotation, has_text_layer=p.has_text_layer) for p in pages],
        extraction=ExtractionRef(id=extraction.id, status=extraction.status, model_name=extraction.model_name, created_at=extraction.created_at) if extraction else None,
    )


@router.post("/{document_id}/reprocess", response_model=ReprocessResponse, status_code=202)
async def reprocess_document(
    document_id: uuid.UUID,
    payload: ReprocessRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    document = _get_document_or_404(db, document_id)
    job = Job(job_type="process_document", target_id=document_id, target_name=document.original_name, status="QUEUED")
    db.add(job)
    db.commit()

    if payload.from_step is None:
        if not document.original_path:
            raise ApiError(409, "INVALID_STATE", "원본 파일을 찾을 수 없어 처음부터 재처리할 수 없습니다")
        default_queue.enqueue(run_document_pipeline, document_id, job.id)
    else:
        if payload.from_step in ("extract", "risk") and not db.query(OcrLine).filter(OcrLine.document_id == document_id).first():
            raise ApiError(409, "INVALID_STATE", "OCR 결과가 없어 해당 단계부터 재처리할 수 없습니다")
        if payload.from_step == "risk" and not db.query(Extraction).filter(Extraction.document_id == document_id).first():
            raise ApiError(409, "INVALID_STATE", "추출 결과가 없어 위험조항만 재처리할 수 없습니다")
        default_queue.enqueue(run_reprocess, document_id, job.id, payload.from_step)

    return ReprocessResponse(job_id=job.id)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    _get_document_or_404(db, document_id)
    # ORM session.delete()는 로드된 관계를 기본적으로 "연결 해제(FK NULL)"하려 시도해 NOT NULL 제약과 충돌한다.
    # bulk delete로 순수 SQL DELETE를 보내 DB의 ON DELETE CASCADE(FK ondelete="CASCADE")가 하위 행을 정리하게 한다.
    db.query(Document).filter(Document.id == document_id).delete()
    db.commit()
