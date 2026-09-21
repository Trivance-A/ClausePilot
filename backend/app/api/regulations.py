import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.storage import regulations_dir, save_upload
from app.db.session import get_db
from app.models.job import Job
from app.models.regulation import Regulation, RegulationChunk, RegulationNode
from app.models.user import User
from app.schemas.regulation import (
    ReindexRequest,
    ReindexResponse,
    RegNode,
    RegNodeContent,
    RegulationDetail,
    RegulationListItem,
    UploadRegulationResponse,
)
from app.services.pipeline import run_regulation_pipeline

router = APIRouter(prefix="/regulations", tags=["regulations"])


def _to_list_item(r: Regulation) -> RegulationListItem:
    return RegulationListItem(
        id=r.id, title=r.title, doc_type=r.doc_type, version=r.version, status=r.status,
        chunk_count=r.chunk_count, effective_date=r.effective_date, created_at=r.created_at, error=r.error,
    )


def _build_tree(nodes: list[RegulationNode]) -> list[RegNode]:
    children_of: dict[uuid.UUID | None, list[RegulationNode]] = {}
    for n in nodes:
        children_of.setdefault(n.parent_id, []).append(n)
    for lst in children_of.values():
        lst.sort(key=lambda n: n.sort_order)

    def build(parent_id: uuid.UUID | None) -> list[RegNode]:
        return [
            RegNode(node_id=n.id, level=n.level, number=n.number, title=n.title, path=n.path, page_no=n.page_no, children=build(n.id))
            for n in children_of.get(parent_id, [])
        ]

    return build(None)


@router.get("")
async def list_regulations(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> dict[str, list[RegulationListItem]]:
    regs = db.query(Regulation).order_by(Regulation.created_at.desc()).all()
    return {"items": [_to_list_item(r) for r in regs]}


@router.post("", response_model=UploadRegulationResponse, status_code=202)
async def upload_regulation(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: Literal["정관", "규정", "지침", "매뉴얼"] = Form(...),
    effective_date: str | None = Form(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    previous = db.query(Regulation).filter(Regulation.title == title, Regulation.status != "ARCHIVED").all()
    for p in previous:
        p.status = "ARCHIVED"

    reg_id = uuid.uuid4()
    content = await file.read()
    path = save_upload(regulations_dir(), reg_id, file.filename or f"{reg_id}.pdf", content)
    version = (max((p.version for p in previous), default=0)) + 1

    parsed_effective_date = None
    if effective_date:
        try:
            parsed_effective_date = date.fromisoformat(effective_date[:10])
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", "effective_date는 YYYY-MM-DD 형식이어야 합니다")

    regulation = Regulation(id=reg_id, title=title, doc_type=doc_type, version=version, status="UPLOADED", source_pdf_path=path, effective_date=parsed_effective_date)
    db.add(regulation)
    job = Job(job_type="index_regulation", target_id=reg_id, target_name=title, status="QUEUED")
    db.add(job)
    db.commit()

    background_tasks.add_task(run_regulation_pipeline, reg_id, job.id)
    return UploadRegulationResponse(regulation_id=reg_id, job_id=job.id, version=version, status="UPLOADED")


def _get_or_404(db: Session, regulation_id: uuid.UUID) -> Regulation:
    reg = db.get(Regulation, regulation_id)
    if not reg:
        raise ApiError(404, "NOT_FOUND", "규정을 찾을 수 없습니다")
    return reg


@router.get("/{regulation_id}/pdf")
async def get_regulation_pdf(regulation_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reg = _get_or_404(db, regulation_id)
    if not reg.source_pdf_path:
        raise ApiError(409, "INVALID_STATE", "원본 PDF가 없습니다")
    return FileResponse(reg.source_pdf_path, media_type="application/pdf")


@router.get("/{regulation_id}/nodes/{node_id}", response_model=RegNodeContent)
async def get_regulation_node(regulation_id: uuid.UUID, node_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    node = db.query(RegulationNode).filter(RegulationNode.id == node_id, RegulationNode.regulation_id == regulation_id).one_or_none()
    if not node:
        raise ApiError(404, "NOT_FOUND", "노드를 찾을 수 없습니다")
    chunk_ids = [c.id for c in db.query(RegulationChunk).filter(RegulationChunk.node_id == node_id).all()]
    return RegNodeContent(node_id=node.id, path=node.path, content=node.content, page_no=node.page_no, bbox=tuple(node.bbox) if node.bbox else None, chunk_ids=chunk_ids)


@router.get("/{regulation_id}", response_model=RegulationDetail)
async def get_regulation(regulation_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reg = _get_or_404(db, regulation_id)
    tree: list[RegNode] = []
    if reg.status == "INDEXED":
        nodes = db.query(RegulationNode).filter(RegulationNode.regulation_id == regulation_id).all()
        tree = _build_tree(nodes)
    return RegulationDetail(**_to_list_item(reg).model_dump(), tree=tree)


@router.post("/{regulation_id}/reindex", response_model=ReindexResponse, status_code=202)
async def reindex_regulation(regulation_id: uuid.UUID, payload: ReindexRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reg = _get_or_404(db, regulation_id)
    db.query(RegulationChunk).filter(RegulationChunk.regulation_id == regulation_id).delete()
    db.query(RegulationNode).filter(RegulationNode.regulation_id == regulation_id).delete()
    reg.status, reg.error, reg.chunk_count = "PARSING", None, None
    job = Job(job_type="index_regulation", target_id=regulation_id, target_name=reg.title, status="QUEUED")
    db.add(job)
    db.commit()
    background_tasks.add_task(run_regulation_pipeline, regulation_id, job.id)
    return ReindexResponse(job_id=job.id)


@router.delete("/{regulation_id}", status_code=204)
async def delete_regulation(regulation_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reg = _get_or_404(db, regulation_id)
    reg.status = "ARCHIVED"
    db.commit()
