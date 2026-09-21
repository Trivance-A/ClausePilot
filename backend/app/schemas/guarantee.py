import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.document import RiskSummary
from app.schemas.extraction import FieldCode

GuaranteeType = Literal["contract", "bid", "defect", "payment", "advance", "other"]
GUARANTEE_TYPE_LABELS: dict[str, str] = {
    "contract": "계약보증",
    "bid": "입찰보증",
    "defect": "하자보증",
    "payment": "지급보증",
    "advance": "선급금보증",
    "other": "기타",
}


class GuaranteePeriod(BaseModel):
    start: str | None
    end: str | None


class GuaranteeFormValues(BaseModel):
    contract_name: str | None
    contract_amount: float | None
    guarantee_amount: float | None
    contract_date: str | None
    performance_due_date: str | None
    guarantee_period: GuaranteePeriod | None
    creditor_name: str | None
    creditor_biz_no: str | None


class FieldSource(BaseModel):
    field_id: str
    confidence: float
    highlight_ids: list[uuid.UUID]
    page_no: int | None


class GuaranteeApplication(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    guarantee_type: GuaranteeType
    status: Literal["DRAFT", "SUBMITTED"]
    form_values: GuaranteeFormValues
    field_sources: dict[str, FieldSource]
    required_fields: list[FieldCode]
    viewer_url: str
    risk_summary: RiskSummary | None = None


class CreateGuaranteeRequest(BaseModel):
    document_id: uuid.UUID
    guarantee_type: GuaranteeType


class PatchGuaranteeRequest(BaseModel):
    form_values: GuaranteeFormValues
    status: Literal["DRAFT", "SUBMITTED"] | None = None
