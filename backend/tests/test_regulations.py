from tests.helpers import upload_and_wait_regulation
from tests.pdf_fixtures import regulation_pdf_bytes


def test_regulation_upload_parses_tree(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="계약사무규정")
    r = client.get(f"/api/v1/regulations/{reg_id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "INDEXED"
    top_paths = [n["path"] for n in body["tree"]]
    assert "제1장" in top_paths and "제3장" in top_paths
    assert body["chunk_count"] > 0


def test_reupload_same_title_archives_previous_version(client, admin_headers):
    upload_and_wait_regulation(client, admin_headers, title="버전관리규정")
    reg_id_v2 = upload_and_wait_regulation(client, admin_headers, title="버전관리규정")

    items = client.get("/api/v1/regulations", headers=admin_headers).json()["items"]
    same_title = [r for r in items if r["title"] == "버전관리규정"]
    assert len(same_title) == 2
    archived = [r for r in same_title if r["id"] != reg_id_v2][0]
    assert archived["status"] == "ARCHIVED"
    current = [r for r in same_title if r["id"] == reg_id_v2][0]
    assert current["version"] == archived["version"] + 1


def test_regulation_node_content(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="노드조회규정")
    tree = client.get(f"/api/v1/regulations/{reg_id}", headers=admin_headers).json()["tree"]
    article = next(n for n in tree if n["path"] == "제1장")["children"][0]

    r = client.get(f"/api/v1/regulations/{reg_id}/nodes/{article['node_id']}", headers=admin_headers)
    assert r.status_code == 200
    assert "목적" in r.json()["content"]


def test_delete_regulation_is_soft_delete(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="삭제테스트규정")
    r = client.delete(f"/api/v1/regulations/{reg_id}", headers=admin_headers)
    assert r.status_code == 204
    r = client.get(f"/api/v1/regulations/{reg_id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "ARCHIVED"


def test_upload_requires_pdf_like_content(client, admin_headers):
    r = client.post(
        "/api/v1/regulations",
        headers=admin_headers,
        files={"file": ("bad.pdf", b"not a real pdf", "application/pdf")},
        data={"title": "손상된규정", "doc_type": "규정"},
    )
    assert r.status_code == 202
    reg_id = r.json()["regulation_id"]

    from tests.helpers import TERMINAL_REGULATION_STATUSES, wait_for

    status = wait_for(lambda: client.get(f"/api/v1/regulations/{reg_id}", headers=admin_headers).json()["status"], TERMINAL_REGULATION_STATUSES)
    assert status == "FAILED"
    assert client.get(f"/api/v1/regulations/{reg_id}", headers=admin_headers).json()["error"]


def test_regulation_pdf_fixture_has_real_korean_text():
    """스모크 테스트 자산 자체의 회귀 방지 — PyMuPDF 기본 폰트로 만들면 한글이 깨진다는 걸 다시 확인."""
    import pymupdf as fitz

    doc = fitz.open(stream=regulation_pdf_bytes(), filetype="pdf")
    text = doc[0].get_text("text")
    doc.close()
    assert "제1장" in text
