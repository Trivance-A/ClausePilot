"""문서/규정 업로드 후 RQ 워커 프로세스(app/core/queue.py)에서 실행되는 파이프라인 함수들.
api 프로세스의 요청 컨텍스트와는 별도 프로세스/세션이므로 매번 새 DB 세션을 연다."""

import uuid
from datetime import datetime, timezone

import app.models  # noqa: F401 - worker 프로세스가 이 모듈만 임포트해도 전체 모델이 Base.metadata에 등록되게 함
from app.core.storage import normalized_dir
from app.db.session import SessionLocal
from app.models.document import Document, OcrLine, Page
from app.models.extraction import Extraction, ExtractionField
from app.models.highlight import Highlight
from app.models.job import Job
from app.models.regulation import Regulation, RegulationChunk, RegulationNode
from app.models.risk import RiskFinding
from app.models.risk_rule import RiskRule
from app.services import ai_client as ai

_FIELD_LABELS = ai.FIELD_LABELS


def _rebuild_node_tree(rows: list[RegulationNode]) -> list[ai.RegulationNodeDict]:
    """DB에 저장된 평면 노드 목록(parent_id만 있음)을 parent_id 기준으로 다시 트리로 묶는다.
    chunk_regulation이 조(article) 노드의 children(항 등)을 순회해 본문을 합치므로,
    children이 실제로 채워진 트리를 넘겨야 한다(평면 목록에 children=[]를 넣으면 안 됨)."""
    children_of: dict[uuid.UUID | None, list[RegulationNode]] = {}
    for r in rows:
        children_of.setdefault(r.parent_id, []).append(r)
    for lst in children_of.values():
        lst.sort(key=lambda r: r.sort_order)

    def build(parent_id: uuid.UUID | None) -> list[ai.RegulationNodeDict]:
        return [
            {
                "level": r.level, "number": r.number, "title": r.title, "path": r.path,
                "page_no": r.page_no, "bbox": r.bbox, "content": r.content, "children": build(r.id),
            }
            for r in children_of.get(parent_id, [])
        ]

    return build(None)


def _active_risk_rules(db) -> list[ai.RiskRuleDict]:
    rows = db.query(RiskRule).filter(RiskRule.enabled.is_(True)).all()
    return [
        {
            "rule_code": r.rule_code,
            "category": r.category,
            "rule_type": r.rule_type,
            "title": r.title,
            "description": r.description,
            "keywords": r.keywords,
            "field_code": r.field_code,
            "base_score": r.base_score,
        }
        for r in rows
    ]


def _fail(db, document: Document | None, regulation: Regulation | None, job: Job, step: str, reason: str) -> None:
    if document:
        document.status = "FAILED"
        document.failure_step = step
        document.failure_reason = reason
    if regulation:
        regulation.status = "FAILED"
        regulation.error = f"{step}: {reason}"
    job.status = "FAILED"
    job.current_step = step
    job.error = reason
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def run_document_pipeline(document_id: uuid.UUID, job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        job = db.get(Job, job_id)
        if not document or not job:
            return

        job.status, job.started_at, job.attempts = "RUNNING", datetime.now(timezone.utc), job.attempts + 1
        db.commit()

        try:
            document.status, job.current_step, job.progress = "NORMALIZING", "normalize", 10
            db.commit()
            norm_path = str(normalized_dir() / f"{document.id}.pdf")
            normalized = ai.normalize_to_pdf(document.original_path, document.original_format, norm_path)
        except (ai.UnsupportedFormatError, ValueError) as exc:
            # ValueError: hwp5txt 등 외부 파서 실행 실패(손상된 파일 등)도 실패로 분류
            _fail(db, document, None, job, "normalize", str(exc))
            return

        document.normalized_pdf_path = normalized["normalized_pdf_path"]
        document.page_count = len(normalized["pages"])
        has_text = any(p["has_text_layer"] for p in normalized["pages"])
        document.source_type = "native" if has_text else "scan"
        for p in normalized["pages"]:
            db.add(Page(document_id=document.id, **p))
        db.commit()

        document.status, job.current_step, job.progress = "OCR", "ocr", 35
        db.commit()
        ocr_lines = ai.run_ocr(document.normalized_pdf_path)
        for line in ocr_lines:
            db.add(OcrLine(document_id=document.id, **line))
        db.commit()

        document.status, job.current_step, job.progress = "EXTRACTING", "extract", 60
        db.commit()
        fields = ai.extract_contract_fields(ocr_lines)
        extraction = Extraction(document_id=document.id, status="AUTO", model_name="rule-based-v1")
        db.add(extraction)
        db.flush()
        for f in fields:
            highlights = f.pop("highlights")
            field_row = ExtractionField(extraction_id=extraction.id, label=_FIELD_LABELS[f["field_code"]], color_key=f["field_code"], **f)
            db.add(field_row)
            db.flush()
            for h in highlights:
                db.add(Highlight(document_id=document.id, extraction_field_id=field_row.id, origin="auto", **h))
        db.commit()

        document.status, job.current_step, job.progress = "RISK", "risk", 85
        db.commit()
        risks = ai.detect_risks(ocr_lines, fields, _active_risk_rules(db))
        for r in risks:
            highlights = r.pop("highlights")
            risk_row = RiskFinding(document_id=document.id, status="OPEN", **r)
            db.add(risk_row)
            db.flush()
            for h in highlights:
                db.add(Highlight(document_id=document.id, risk_finding_id=risk_row.id, origin="auto", **h))
        db.commit()

        document.status = "DONE"
        job.status, job.current_step, job.progress = "DONE", None, 100
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def run_reprocess(document_id: uuid.UUID, job_id: uuid.UUID, from_step: str) -> None:
    """from_step(ocr|extract|risk)부터 이미 저장된 ocr_lines/fields를 재사용해 이후 단계만 다시 실행한다."""
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        job = db.get(Job, job_id)
        if not document or not job:
            return
        job.status, job.started_at, job.attempts = "RUNNING", datetime.now(timezone.utc), job.attempts + 1
        db.commit()

        if from_step == "ocr":
            document.status, job.current_step, job.progress = "OCR", "ocr", 35
            db.commit()
            db.query(OcrLine).filter(OcrLine.document_id == document.id).delete()
            ocr_lines = ai.run_ocr(document.normalized_pdf_path)
            for line in ocr_lines:
                db.add(OcrLine(document_id=document.id, **line))
            db.commit()
        else:
            ocr_lines = [
                {"page_no": l.page_no, "line_id": l.line_id, "text": l.text, "bbox": l.bbox, "confidence": l.confidence, "source": l.source, "table_cell": l.table_cell}
                for l in db.query(OcrLine).filter(OcrLine.document_id == document.id).all()
            ]

        fields: list[ai.ExtractionFieldDict]
        if from_step in ("ocr", "extract"):
            document.status, job.current_step, job.progress = "EXTRACTING", "extract", 60
            db.commit()
            extraction = db.query(Extraction).filter(Extraction.document_id == document.id).one()
            db.query(ExtractionField).filter(ExtractionField.extraction_id == extraction.id).delete()
            extraction.status = "AUTO"
            fields = ai.extract_contract_fields(ocr_lines)
            for f in fields:
                highlights = f.pop("highlights")
                field_row = ExtractionField(extraction_id=extraction.id, label=_FIELD_LABELS[f["field_code"]], color_key=f["field_code"], **f)
                db.add(field_row)
                db.flush()
                for h in highlights:
                    db.add(Highlight(document_id=document.id, extraction_field_id=field_row.id, origin="auto", **h))
            db.commit()
        else:
            extraction = db.query(Extraction).filter(Extraction.document_id == document.id).one()
            fields = [
                {"field_code": f.field_code, "raw_value": f.raw_value, "normalized_value": f.normalized_value, "confidence": f.confidence, "mapping_method": f.mapping_method}
                for f in extraction.fields
            ]

        document.status, job.current_step, job.progress = "RISK", "risk", 85
        db.commit()
        db.query(RiskFinding).filter(RiskFinding.document_id == document.id).delete()
        risks = ai.detect_risks(ocr_lines, fields, _active_risk_rules(db))
        for r in risks:
            highlights = r.pop("highlights")
            risk_row = RiskFinding(document_id=document.id, status="OPEN", **r)
            db.add(risk_row)
            db.flush()
            for h in highlights:
                db.add(Highlight(document_id=document.id, risk_finding_id=risk_row.id, origin="auto", **h))
        db.commit()

        document.status = "DONE"
        job.status, job.current_step, job.progress = "DONE", None, 100
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def run_regulation_pipeline(regulation_id: uuid.UUID, job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        regulation = db.get(Regulation, regulation_id)
        job = db.get(Job, job_id)
        if not regulation or not job:
            return
        job.status, job.started_at, job.attempts = "RUNNING", datetime.now(timezone.utc), job.attempts + 1
        db.commit()

        regulation.status, job.current_step, job.progress = "PARSING", "parse", 20
        db.commit()
        try:
            nodes = ai.parse_regulation_structure(regulation.source_pdf_path)
        except Exception as exc:  # noqa: BLE001 - PDF가 아니거나 손상된 경우까지 폭넓게 포착해 FAILED로 기록
            _fail(db, None, regulation, job, "parse", str(exc))
            return

        def _save(node_list: list[ai.RegulationNodeDict], parent_id: uuid.UUID | None, order_start: int) -> int:
            order = order_start
            for n in node_list:
                children = n.pop("children")
                row = RegulationNode(regulation_id=regulation.id, parent_id=parent_id, sort_order=order, **n)
                db.add(row)
                db.flush()
                order += 1
                _save(children, row.id, 0)
            return order

        _save(nodes, None, 0)
        db.commit()

        job.current_step, job.progress = "chunk", 60
        db.commit()
        all_nodes = db.query(RegulationNode).filter(RegulationNode.regulation_id == regulation.id).all()
        node_by_path = {n.path: n for n in all_nodes}
        chunks = ai.chunk_regulation(_rebuild_node_tree(all_nodes))
        embeddings = ai.index_chunks(chunks)
        for c, embedding in zip(chunks, embeddings, strict=True):
            node = node_by_path.get(c["node_path"])
            db.add(RegulationChunk(regulation_id=regulation.id, node_id=node.id if node else None, content=c["content"], embedding=embedding))
        db.commit()

        regulation.status = "INDEXED"
        regulation.chunk_count = len(chunks)
        job.status, job.current_step, job.progress = "DONE", None, 100
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
