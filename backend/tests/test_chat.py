import uuid


def test_list_chat_sessions_route_exists(client):
    response = client.get("/api/v1/chat/sessions")

    assert response.status_code == 501


def test_create_chat_session_route_exists(client):
    response = client.post("/api/v1/chat/sessions", json={"regulation_ids": []})

    assert response.status_code == 501


def test_list_chat_messages_route_exists(client):
    response = client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}/messages")

    assert response.status_code == 501


def test_post_chat_message_route_exists(client):
    response = client.post(
        f"/api/v1/chat/sessions/{uuid.uuid4()}/messages",
        json={"content": "출장비 정산 기한이 어떻게 되나요?", "stream": False},
    )

    assert response.status_code == 501


def test_post_chat_message_rejects_missing_content(client):
    response = client.post(f"/api/v1/chat/sessions/{uuid.uuid4()}/messages", json={})

    assert response.status_code == 422


def test_message_feedback_route_exists(client):
    response = client.post(f"/api/v1/chat/messages/{uuid.uuid4()}/feedback", json={"rating": 1})

    assert response.status_code == 501
