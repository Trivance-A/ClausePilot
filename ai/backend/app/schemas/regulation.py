import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import BBox

RegulationStatus = Literal["UPLOADED", "PARSING", "INDEXED", "FAILED", "ARCHIVED"]
RegDocType = Literal["정관", "규정", "지침", "매뉴얼"]
RegNodeLevel = Literal["chapter", "section", "article", "paragraph", "item", "subitem", "appendix"]


class RegulationListItem(BaseModel):
    id: uuid.UUID
    title: str
    doc_type: RegDocType
    version: int
    status: RegulationStatus
    chunk_count: int | None
    effective_date: date | None
    created_at: datetime
    error: str | None = None


class RegNode(BaseModel):
    node_id: uuid.UUID
    level: RegNodeLevel
    number: str
    title: str | None
    path: str | None = None
    page_no: int | None = None
    children: list["RegNode"] = []


class RegulationDetail(RegulationListItem):
    tree: list[RegNode]


class RegNodeContent(BaseModel):
    node_id: uuid.UUID
    path: str
    content: str
    page_no: int | None
    bbox: BBox | None
    chunk_ids: list[uuid.UUID]


class UploadRegulationResponse(BaseModel):
    regulation_id: uuid.UUID
    job_id: uuid.UUID
    version: int
    status: RegulationStatus


class ReindexRequest(BaseModel):
    chunk_strategy: Literal["article", "paragraph"] | None = None


class ReindexResponse(BaseModel):
    job_id: uuid.UUID
