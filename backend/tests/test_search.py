from tests.helpers import upload_and_wait_regulation


def test_hybrid_search_ranks_relevant_article_first(client, admin_headers):
    upload_and_wait_regulation(client, admin_headers, title="검색테스트규정")
    r = client.post("/api/v1/search", headers=admin_headers, json={"query": "계약보증금", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]
    top = body["results"][0]
    assert "계약보증금" in top["path"] or "계약보증금" in top["content"]
    assert top["bm25_score"] >= 0
    assert top["rrf_score"] >= 0


def test_search_response_shape_is_always_valid(client, admin_headers):
    r = client.post("/api/v1/search", headers=admin_headers, json={"query": "존재하지않는검색어xyz123"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["results"], list)
    assert isinstance(body["latency_ms"], int)
