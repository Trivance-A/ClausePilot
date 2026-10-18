def test_login_success(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin"
    assert body["access_token"]


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_with_token(client, admin_headers):
    r = client.get("/api/v1/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "admin@example.com"
