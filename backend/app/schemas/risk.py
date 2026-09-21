import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Severity
from app.schemas.document import RiskSummary
from app.schemas.extraction import Highlight

RiskStatus = Literal["OPEN", "ACKNOWLEDGED", "DISMISSED"]
RiskCategory = Literal["penalty", "missing", "contradiction", "toxic", "policy"]


class RiskFinding(BaseModel):
    id: uuid.UUID
    category: RiskCategory
    severity: Severity
    score: float
    rule_code: str | None
    title: str
    description: str
    evidence_text: str | None
    highlights: list[Highlight]
    llm_reasoning: dict | None
    status: RiskStatus
    note: str | None = None


class RisksResponse(BaseModel):
    items: list[RiskFinding]
    summary: RiskSummary


class PatchRiskRequest(BaseModel):
    status: RiskStatus
    note: str | None = None


class RerunResponse(BaseModel):
    job_id: uuid.UUID
