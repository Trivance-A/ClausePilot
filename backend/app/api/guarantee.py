import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.extraction import Extraction, ExtractionField
from app.models.guarantee import GuaranteeApplication as GuaranteeApplicationModel
from app.models.risk import RiskFinding
from app.models.user import User
from app.schemas.guarantee import (
    REQUIRED_FIELDS,
    CreateGuaranteeRequest,
    FieldSource,
    GuaranteeApplication,
    GuaranteeFormValues,
    GuaranteePeriod,
    PatchGuaranteeRequest,
)

router = APIRouter(prefix="/guarantee-applications", tags=["guarantee-applications"])


def _risk_summary(db: Session, document_id: uuid.UUID) -> dict[str, int] | None:
    risks = db.query(RiskFinding).filter(RiskFinding.document_id == document_id).all()
    if not risks:
        return None
    summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in risks:
        if r.status != "DISMISSED":
            summary[r.severity] += 1
    return summary


def _build_form_values(fields_by_code: dict[str, ExtractionField]) -> GuaranteeFormValues:
    def text_of(code: str) -> str | None:
        f = fields_by_code.get(code)
        if not f:
            return None
        nv = f.normalized_value or {}
        return nv.get("text") or f.raw_value

    def amount_of(code: str) -> float | None:
        f = fields_by_code.get(code)
        return (f.normalized_value or {}).get("amount") if f else None

    def date_of(code: str) -> str | None:
        f = fields_by_code.get(code)
        return (f.normalized_value or {}).get("date") if f else None

    period_field = fields_by_code.get("guarantee_period")
    period_nv = (period_field.normalized_value or {}) if period_field else {}
    period = GuaranteePeriod(start=period_nv.get("start"), end=period_nv.get("end")) if period_nv.get("start") else None

    return GuaranteeFormValues(
        contract_name=text_of("contract_name"),
        contract_amount=amount_of("contract_amount"),
        guarantee_amount=amount_of("guarantee_amount"),
        contract_date=date_of("contract_date"),
        performance_due_date=date_of("performance_due_date"),
        guarantee_period=period,
        creditor_name=text_of("creditor_name"),
        creditor_biz_no=(fields_by_code.get("creditor_biz_no").normalized_value or {}).get("text") if fields_by_code.get("creditor_biz_no") else None,
    )


def _to_out(app_row: GuaranteeApplicationModel, db: Session) -> GuaranteeApplication:
    return GuaranteeApplication(
        id=app_row.id,
        document_id=app_row.document_id,
        guarantee_type=app_row.guarantee_type,
        status=app_row.status,
        form_values=GuaranteeFormValues(**app_row.form_values),
        field_sources={k: FieldSource(**v) for k, v in app_row.field_sources.items()},
        required_fields=app_row.required_fields,
        viewer_url=f"/documents/{app_row.document_id}/viewer?field=contract_amount",
        risk_summary=_risk_summary(db, app_row.document_id),
    )


@router.post("", response_model=GuaranteeApplication, status_code=201)
async def create_guarantee_application(payload: CreateGuaranteeRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    extraction = db.query(Extraction).filter(Extraction.document_id == payload.document_id).one_or_none()
    if not extraction:
        raise ApiError(409, "INVALID_STATE", "분석이 완료되지 않은 문서입니다")

    fields_by_code = {f.field_code: f for f in extraction.fields}
    form_values = _build_form_values(fields_by_code)

    field_sources: dict[str, dict] = {}
    for code, f in fields_by_code.items():
        if f.raw_value:
            field_sources[code] = {
                "field_id": f"f-{code}",
                "confidence": f.confidence,
                "highlight_ids": [str(h.id) for h in f.highlights],
                "page_no": f.highlights[0].page_no if f.highlights else None,
            }

    app_row = GuaranteeApplicationModel(
        document_id=payload.document_id,
        guarantee_type=payload.guarantee_type,
        status="DRAFT",
        form_values=form_values.model_dump(),
        field_sources=field_sources,
        required_fields=REQUIRED_FIELDS[payload.guarantee_type],
    )
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return _to_out(app_row, db)


@router.get("/{application_id}", response_model=GuaranteeApplication)
async def get_guarantee_application(application_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    app_row = db.get(GuaranteeApplicationModel, application_id)
    if not app_row:
        raise ApiError(404, "NOT_FOUND", "보증신청서를 찾을 수 없습니다")
    return _to_out(app_row, db)


@router.patch("/{application_id}", response_model=GuaranteeApplication)
async def patch_guarantee_application(application_id: uuid.UUID, payload: PatchGuaranteeRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    app_row = db.get(GuaranteeApplicationModel, application_id)
    if not app_row:
        raise ApiError(404, "NOT_FOUND", "보증신청서를 찾을 수 없습니다")
    app_row.form_values = payload.form_values.model_dump()
    if payload.status:
        app_row.status = payload.status
    db.commit()
    db.refresh(app_row)
    return _to_out(app_row, db)
