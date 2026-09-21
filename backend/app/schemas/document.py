import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import BBox, Severity

DocumentStatus = Literal["UPLOADED", "NORMALIZING", "OCR", "EXTRACTING", "RISK", "DONE", "FAILED"]
SourceType = Literal["native", "scan", "mixed"]
RiskSummary = dict[Severity, int]


class DocumentListItem(BaseModel):
    id: uuid.UUID
    original_name: str
    original_format: str
    source_type: SourceType | None
    page_count: int | None
    status: DocumentStatus
    risk_summary: RiskSummary | None
    created_at: datetime


class PageMeta(BaseModel):
    page_no: int
    width_pt: float
    height_pt: float
    rotation: int
    has_text_layer: bool


class ExtractionRef(BaseModel):
    id: uuid.UUID
    status: Literal["AUTO", "REVIEWED", "CONFIRMED"]
    model_name: str
    created_at: datetime


class DocumentDetail(DocumentListItem):
    pages: list[PageMeta]
    extraction: ExtractionRef | None


JobStep = Literal["normalize", "ocr", "extract", "risk"] | str
JobStatus = Literal["QUEUED", "RUNNING", "DONE", "FAILED"]


class Job(BaseModel):
    id: uuid.UUID
    current_step: JobStep | None
    progress: int
    error: str | None
    status: JobStatus | None = None


class DocumentStatusResponse(BaseModel):
    status: DocumentStatus
    job: Job | None


class UploadItem(BaseModel):
    document_id: uuid.UUID
    job_id: uuid.UUID
    original_name: str
    status: DocumentStatus


class UploadResponse(BaseModel):
    items: list[UploadItem]


class OcrLineOut(BaseModel):
    id: uuid.UUID
    line_id: str
    text: str
    bbox: BBox
    confidence: float
    source: str
    table_cell: str | None


class LinesResponse(BaseModel):
    page_no: int
    lines: list[OcrLineOut]


class ReprocessRequest(BaseModel):
    from_step: Literal["ocr", "extract", "risk"] | None = None
    ocr_engine: str | None = None


class ReprocessResponse(BaseModel):
    job_id: uuid.UUID
