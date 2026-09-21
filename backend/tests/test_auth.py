def test_login_route_exists(client):
    response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "x"})

    assert response.status_code == 501


def test_me_route_exists(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 501
