import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import BBox

FieldCode = Literal[
    "contract_name",
    "contract_amount",
    "guarantee_amount",
    "contract_date",
    "performance_due_date",
    "guarantee_period",
    "creditor_name",
    "creditor_biz_no",
]
FIELD_CODES: list[FieldCode] = [
    "contract_name",
    "contract_amount",
    "guarantee_amount",
    "contract_date",
    "performance_due_date",
    "guarantee_period",
    "creditor_name",
    "creditor_biz_no",
]
FIELD_LABELS: dict[str, str] = {
    "contract_name": "계약건명",
    "contract_amount": "계약금액",
    "guarantee_amount": "보증금액",
    "contract_date": "계약일자",
    "performance_due_date": "계약이행기일",
    "guarantee_period": "보증기간",
    "creditor_name": "채권자명",
    "creditor_biz_no": "채권자 사업자번호",
}

MappingMethod = Literal["exact", "fuzzy", "llm_ref", "manual", "none"]
HighlightOrigin = Literal["auto", "manual"]
ExtractionStatus = Literal["AUTO", "REVIEWED", "CONFIRMED"]

# 프론트 NormalizedValue 유니온을 느슨한 dict로 받는다.
# 실제 형태는 필드에 따라 {"amount": number} | {"date": "YYYY-MM-DD"} | {"start","end"} | {"text": str} 중 하나.
NormalizedValue = dict | None


class Highlight(BaseModel):
    id: uuid.UUID
    page_no: int
    bbox: BBox
    origin: HighlightOrigin
    ocr_line_id: str | None = None


class ExtractionField(BaseModel):
    field_code: FieldCode
    label: str
    color_key: str | None = None
    raw_value: str | None
    normalized_value: NormalizedValue
    confidence: float
    mapping_method: MappingMethod
    is_confirmed: bool
    reviewer_note: str | None = None
    highlights: list[Highlight]


class ExtractionResponse(BaseModel):
    extraction_id: uuid.UUID
    status: ExtractionStatus
    fields: list[ExtractionField]
    color_map: dict[str, str]  # 항목 색상의 단일 소스. 프론트에 색상을 하드코딩하지 않는다.


class FieldPatch(BaseModel):
    raw_value: str | None = None
    normalized_value: NormalizedValue = None
    is_confirmed: bool | None = None
    reviewer_note: str | None = None


class CreateHighlightBody(BaseModel):
    """field_code 또는 risk_finding_id 중 정확히 하나만 채워서 보낸다 (둘 다 없거나 둘 다 있으면 400)."""

    field_code: FieldCode | None = None
    risk_finding_id: uuid.UUID | None = None
    page_no: int
    bbox: BBox


class PatchHighlightRequest(BaseModel):
    bbox: BBox
    page_no: int | None = None
