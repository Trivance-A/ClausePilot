from tests.helpers import upload_and_wait_document


def test_admin_stats_requires_admin_role(client, user_headers):
    r = client.get("/api/v1/admin/stats", headers=user_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_admin_stats_reflects_uploaded_documents(client, admin_headers):
    upload_and_wait_document(client, admin_headers)
    r = client.get("/api/v1/admin/stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["documents"]["total"] >= 1
    assert body["documents"]["done"] >= 1


def test_admin_jobs_lists_process_document_jobs(client, admin_headers):
    upload_and_wait_document(client, admin_headers)
    r = client.get("/api/v1/admin/jobs", headers=admin_headers, params={"status": "DONE"})
    assert r.status_code == 200
    assert any(j["job_type"] == "process_document" for j in r.json()["items"])


def test_admin_chat_logs_csv_export(client, admin_headers):
    r = client.get("/api/v1/admin/logs/chat", headers=admin_headers, params={"format": "csv"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
