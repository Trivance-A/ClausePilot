def test_admin_stats_route_exists(client):
    response = client.get("/api/v1/admin/stats")

    assert response.status_code == 501


def test_admin_jobs_route_exists(client):
    response = client.get("/api/v1/admin/jobs", params={"status": "RUNNING"})

    assert response.status_code == 501


def test_admin_chat_logs_route_exists(client):
    response = client.get("/api/v1/admin/logs/chat", params={"page": 1, "size": 20})

    assert response.status_code == 501


def test_admin_chat_logs_csv_route_exists(client):
    response = client.get("/api/v1/admin/logs/chat", params={"format": "csv"})

    assert response.status_code == 501
