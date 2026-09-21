def test_debug_search_route_exists(client):
    response = client.post("/api/v1/search", json={"query": "계약보증금"})

    assert response.status_code == 501
