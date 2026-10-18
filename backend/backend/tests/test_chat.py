from tests.helpers import upload_and_wait_regulation


def _create_session(client, headers, regulation_id: str) -> str:
    r = client.post("/api/v1/chat/sessions", headers=headers, json={"regulation_ids": [regulation_id]})
    assert r.status_code == 201
    return r.json()["session_id"]


def test_chat_answers_with_citations(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="챗봇테스트규정")
    sid = _create_session(client, admin_headers, reg_id)

    r = client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=admin_headers, json={"content": "계약보증금은 얼마인가요?", "stream": False})
    assert r.status_code == 200
    body = r.json()
    assert body["answer_status"] == "ANSWERED"
    assert body["citations"]
    assert body["citations"][0]["regulation_id"] == reg_id


def test_chat_not_found_when_no_match(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="챗봇테스트규정2")
    sid = _create_session(client, admin_headers, reg_id)

    r = client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=admin_headers, json={"content": "오늘 점심 메뉴 추천해줘", "stream": False})
    assert r.status_code == 200
    body = r.json()
    assert body["answer_status"] == "NOT_FOUND"
    assert body["citations"] == []


def test_chat_streaming_emits_sse_events(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="챗봇스트리밍규정")
    sid = _create_session(client, admin_headers, reg_id)

    with client.stream("POST", f"/api/v1/chat/sessions/{sid}/messages", headers=admin_headers, json={"content": "계약보증금은 얼마인가요?"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())
    assert "event: status" in text
    assert "event: token" in text
    assert "event: citation" in text
    assert "event: done" in text


def test_chat_sessions_are_scoped_to_owner(client, admin_headers, user_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="세션격리규정")
    sid = _create_session(client, admin_headers, reg_id)

    r = client.get(f"/api/v1/chat/sessions/{sid}/messages", headers=user_headers)
    assert r.status_code == 403


def test_message_feedback(client, admin_headers):
    reg_id = upload_and_wait_regulation(client, admin_headers, title="피드백규정")
    sid = _create_session(client, admin_headers, reg_id)
    answer = client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=admin_headers, json={"content": "계약보증금은?", "stream": False}).json()

    r = client.post(f"/api/v1/chat/messages/{answer['id']}/feedback", headers=admin_headers, json={"rating": 1})
    assert r.status_code == 201
    assert r.json()["ok"] is True
