import uuid

from sqlalchemy.orm import Session

from app.models.regulation import Regulation, RegulationChunk, RegulationNode
from app.services import ai_client as ai


def search(db: Session, query: str, regulation_ids: list[uuid.UUID] | None, top_k: int = 5) -> list[ai.SearchResultDict]:
    """DB에서 검색 후보(청크)를 조회해 ai_client.hybrid_search에 넘긴다 (AI 모듈은 DB에 직접 접근하지 않는다)."""
    q = (
        db.query(RegulationChunk, Regulation, RegulationNode)
        .join(Regulation, RegulationChunk.regulation_id == Regulation.id)
        .outerjoin(RegulationNode, RegulationChunk.node_id == RegulationNode.id)
        .filter(Regulation.status == "INDEXED")
    )
    if regulation_ids:
        q = q.filter(RegulationChunk.regulation_id.in_(regulation_ids))

    candidates: list[ai.SearchCandidate] = [
        {
            "chunk_id": str(chunk.id),
            "regulation_id": str(reg.id),
            "regulation_title": reg.title,
            "path": node.path if node else "",
            "content": chunk.content,
            "node_id": str(node.id) if node else None,
            "page_no": node.page_no if node else None,
            "bbox": tuple(node.bbox) if node and node.bbox else None,
        }
        for chunk, reg, node in q.all()
    ]
    return ai.hybrid_search(query, candidates, top_k)
