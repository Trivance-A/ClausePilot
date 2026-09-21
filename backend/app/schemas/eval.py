import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.admin import JobStatus
from app.schemas.extraction import FieldCode

EvalSuite = Literal["extraction", "retrieval", "faithfulness", "all"]


class FieldAccuracy(BaseModel):
    overall: float
    by_field: dict[str, float]


class EvalMetrics(BaseModel):
    field_accuracy: FieldAccuracy | None = None
    bbox_mapping_rate: float | None = None
    recall_at_5: float | None = None
    hallucination_rate: float | None = None


class EvalFailure(BaseModel):
    doc_id: uuid.UUID
    doc_name: str | None = None
    field_code: FieldCode
    expected: str
    got: str | None


class EvalRun(BaseModel):
    id: uuid.UUID
    suite: EvalSuite
    status: JobStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: EvalMetrics | None
    failures: list[EvalFailure]


class RunEvalRequest(BaseModel):
    suite: EvalSuite


class RunEvalResponse(BaseModel):
    run_id: uuid.UUID
