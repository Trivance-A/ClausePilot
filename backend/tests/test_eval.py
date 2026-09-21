from tests.helpers import upload_and_wait_document


def test_run_eval_computes_metrics_from_live_data(client, admin_headers):
    upload_and_wait_document(client, admin_headers)
    r = client.post("/api/v1/eval/run", headers=admin_headers, json={"suite": "extraction"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    r = client.get(f"/api/v1/eval/runs/{run_id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DONE"
    assert body["metrics"]["field_accuracy"]["overall"] > 0
    assert body["metrics"]["recall_at_5"] is None  # extraction suite는 retrieval 지표를 채우지 않는다


def test_list_eval_runs(client, admin_headers):
    client.post("/api/v1/eval/run", headers=admin_headers, json={"suite": "all"})
    r = client.get("/api/v1/eval/runs", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1


def test_eval_requires_admin(client, user_headers):
    r = client.post("/api/v1/eval/run", headers=user_headers, json={"suite": "all"})
    assert r.status_code == 403
