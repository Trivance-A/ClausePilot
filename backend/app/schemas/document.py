import uuid

from pydantic import BaseModel


class Evidence(BaseModel):
    page_no: int
    block_id: str | None = None
    bbox: list[float]  # [x0, y0, x1, y1]


class FieldResult(BaseModel):
    value: str | float | None
    confidence: float
    evidence: Evidence | None = None


class RiskFlagOut(BaseModel):
    category: str
    level: str
    description: str
    evidence: Evidence | None = None


class DocumentUploadOut(BaseModel):
    document_id: uuid.UUID
    status: str


class DocumentStatusOut(BaseModel):
    document_id: uuid.UUID
    status: str
    progress: float


class DocumentResultOut(BaseModel):
    document_id: uuid.UUID
    normalized_pdf_url: str
    fields: dict[str, FieldResult]
    risks: list[RiskFlagOut]
