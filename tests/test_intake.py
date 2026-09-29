from tests.test_auth import login, signup


def auth_headers(client, *, email: str, role: str) -> dict[str, str]:
    signup(client, name="Test User", email=email, role=role)
    token = login(client, email=email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_request(client, headers: dict[str, str], request_text: str) -> int:
    response = client.post(
        "/api/requests",
        json={"request_text": request_text},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_reviewer_generates_structured_brief_without_changing_raw_request(client):
    raw_text = "We manually compile a monthly sales dashboard from three systems."
    user_headers = auth_headers(client, email="requester@demo.io", role="USER")
    reviewer_headers = auth_headers(client, email="reviewer@demo.io", role="REVIEWER")
    request_id = create_request(client, user_headers, raw_text)

    response = client.post(
        f"/api/requests/{request_id}/generate-brief",
        headers=reviewer_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "problem_summary": raw_text,
        "likely_users": ["Requesting business team", "Operational stakeholders"],
        "solution_type": "Reporting and analytics solution",
        "clarifying_questions": [
            "What outcome would define success for this request?",
            "Which teams and systems are affected by the current process?",
        ],
        "risks": [
            "Requirements may change after stakeholder discovery.",
            "Dependencies on existing systems have not yet been assessed.",
        ],
        "next_action": "Schedule a discovery session with the requester and key stakeholders.",
    }

    stored = client.get(f"/api/requests/{request_id}", headers=user_headers)
    assert stored.status_code == 200
    assert stored.json()["request_text"] == raw_text


def test_generate_brief_returns_not_found_for_missing_request(client):
    reviewer_headers = auth_headers(client, email="reviewer@demo.io", role="REVIEWER")

    response = client.post(
        "/api/requests/999/generate-brief",
        headers=reviewer_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Request not found: 999"


def test_generate_brief_requires_reviewer(client):
    user_headers = auth_headers(client, email="requester@demo.io", role="USER")
    request_id = create_request(client, user_headers, "Automate a manual intake workflow.")

    response = client.post(
        f"/api/requests/{request_id}/generate-brief",
        headers=user_headers,
    )

    assert response.status_code == 403