import uuid


def test_run_eval_route_exists(client):
    response = client.post("/api/v1/eval/run", json={"suite": "all"})

    assert response.status_code == 501


def test_get_eval_run_route_exists(client):
    response = client.get(f"/api/v1/eval/runs/{uuid.uuid4()}")

    assert response.status_code == 501


def test_list_eval_runs_route_exists(client):
    response = client.get("/api/v1/eval/runs")

    assert response.status_code == 501


def test_run_eval_rejects_invalid_suite(client):
    response = client.post("/api/v1/eval/run", json={"suite": "not_a_real_suite"})

    assert response.status_code == 422
