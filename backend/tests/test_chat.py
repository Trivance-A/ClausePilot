import uuid


def test_create_chat_session_route_exists(client):
    response = client.post("/chat/sessions")

    assert response.status_code == 501


def test_post_chat_message_route_exists(client):
    response = client.post(
        f"/chat/sessions/{uuid.uuid4()}/messages",
        json={"content": "출장비 정산 기한이 어떻게 되나요?"},
    )

    assert response.status_code == 501


def test_post_chat_message_rejects_missing_content(client):
    response = client.post(f"/chat/sessions/{uuid.uuid4()}/messages", json={})

    assert response.status_code == 422
