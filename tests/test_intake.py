import csv
import io
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.models.generated_brief import GeneratedBrief
from app.services.ai_service import (
    AIGenerationError,
    AIOutputValidationError,
    MockAIProvider,
    generate_structured_brief,
)
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


def test_request_submission_generates_and_returns_brief(client):
    user_headers = auth_headers(client, email="auto-brief@demo.io", role="USER")

    response = client.post(
        "/api/requests",
        json={"request_text": "Build a dashboard for monthly service metrics."},
        headers=user_headers,
    )

    assert response.status_code == 201
    request = response.json()
    assert request["brief_generation_status"] == "SUCCEEDED"
    assert request["brief_generation_error"] is None
    assert request["generated_brief"]["solution_type"] == (
        "Reporting and analytics solution"
    )

    stored = client.get(f"/api/requests/{request['id']}", headers=user_headers)
    assert stored.status_code == 200
    assert stored.json()["generated_brief"] == request["generated_brief"]


def test_duplicate_active_request_is_rejected(client):
    user_headers = auth_headers(client, email="duplicate-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="duplicate-reviewer@demo.io", role="REVIEWER"
    )
    description = (
        "We are growing quickly and customer requests are coming through email, "
        "chat, spreadsheets, and different teams."
    )
    request_id = create_request(
        client, user_headers, f"Title: Customer demand visibility\n\n{description}"
    )
    reviewed = client.patch(
        f"/api/requests/{request_id}/triage",
        json={"status": "IN_REVIEW"},
        headers=reviewer_headers,
    )
    assert reviewed.status_code == 200

    duplicate = client.post(
        "/api/requests",
        json={
            "request_text": (
                "Title: A different title\n\n  "
                f"{description.upper().replace(' AND ', '   AND ')}  "
            )
        },
        headers=user_headers,
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == (
        f"Duplicate active request already exists: #{request_id} (IN_REVIEW)"
    )
    mine = client.get("/api/requests/mine", headers=user_headers)
    assert len(mine.json()) == 1


def test_request_submission_survives_brief_generation_failure(client, monkeypatch):
    user_headers = auth_headers(client, email="failed-submit@demo.io", role="USER")

    def failed_generation(_: str):
        raise AIGenerationError("provider unavailable")

    monkeypatch.setattr("app.api.routes.intake.generate_structured_brief", failed_generation)
    response = client.post(
        "/api/requests",
        json={"request_text": "Automate a manual intake workflow."},
        headers=user_headers,
    )

    assert response.status_code == 201
    request = response.json()
    assert request["brief_generation_status"] == "FAILED"
    assert request["brief_generation_error"] == "AI brief generation failed"
    assert request["generated_brief"] is None


def test_reviewer_retries_failed_automatic_brief(client, monkeypatch):
    user_headers = auth_headers(client, email="retry-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="retry-reviewer@demo.io", role="REVIEWER"
    )

    def failed_generation(_: str):
        raise AIGenerationError("provider unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.api.routes.intake.generate_structured_brief", failed_generation
        )
        failed = client.post(
            "/api/requests",
            json={"request_text": "Automate a manual intake workflow."},
            headers=user_headers,
        )

    request_id = failed.json()["id"]
    retried = client.post(
        f"/api/requests/{request_id}/generate-brief",
        headers=reviewer_headers,
    )

    assert retried.status_code == 200
    stored = client.get(f"/api/requests/{request_id}", headers=reviewer_headers)
    request = stored.json()
    assert request["brief_generation_status"] == "SUCCEEDED"
    assert request["brief_generation_error"] is None
    assert request["generated_brief"] == retried.json()


def test_reviewer_exports_all_requests_with_latest_persisted_status(client):
    user_headers = auth_headers(client, email="export-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="export-reviewer@demo.io", role="REVIEWER"
    )
    first_id = create_request(
        client,
        user_headers,
        "Title: Weekly sales reporting\n\nCombine regional sales files.",
    )
    create_request(
        client,
        user_headers,
        "Title: Access request intake\n\nCollect complete application access requests.",
    )
    updated = client.patch(
        f"/api/requests/{first_id}/triage",
        json={"status": "IN_REVIEW", "priority": "HIGH", "owner": "Alex Reviewer"},
        headers=reviewer_headers,
    )
    assert updated.status_code == 200

    response = client.get("/api/requests/export/csv", headers=reviewer_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="requests_export.csv"'
    )
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert list(rows[0]) == [
        "Request Number",
        "Title",
        "Requester",
        "Request Description",
        "Owner",
        "Status",
        "Priority",
        "Created Date",
        "Updated Date",
    ]
    by_title = {row["Title"]: row for row in rows}
    exported = by_title["Weekly sales reporting"]
    assert exported["Request Number"] == "1"
    assert exported["Requester"] == "Test User"
    assert exported["Request Description"] == "Combine regional sales files."
    assert exported["Owner"] == "Alex Reviewer"
    assert exported["Status"] == "IN_REVIEW"
    assert exported["Priority"] == "HIGH"
    assert exported["Created Date"]
    assert exported["Updated Date"]


def test_csv_export_requires_reviewer(client):
    user_headers = auth_headers(client, email="no-export@demo.io", role="USER")

    forbidden = client.get("/api/requests/export/csv", headers=user_headers)
    unauthenticated = client.get("/api/requests/export/csv")

    assert forbidden.status_code == 403
    assert unauthenticated.status_code == 401


def test_status_change_creates_audit_event(client):
    user_headers = auth_headers(client, email="audit-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="audit-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, "Audit this status change.")

    updated = client.patch(
        f"/api/requests/{request_id}/triage",
        json={"status": "IN_REVIEW"},
        headers=reviewer_headers,
    )
    history = client.get(
        f"/api/requests/{request_id}/audit-history", headers=reviewer_headers
    )

    assert updated.status_code == 200
    assert history.status_code == 200
    assert history.json() == [
        {
            "id": 1,
            "request_id": request_id,
            "timestamp": history.json()[0]["timestamp"],
            "event_type": "STATUS_CHANGED",
            "previous_status": "NEW",
            "new_status": "IN_REVIEW",
            "note": None,
            "reviewer_id": 2,
            "reviewer_name": "Test User",
        }
    ]


def test_note_add_and_update_create_append_only_events(client):
    user_headers = auth_headers(client, email="notes-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="notes-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, "Audit these reviewer notes.")

    for note in ["Additional information required", "Information received"]:
        response = client.patch(
            f"/api/requests/{request_id}/triage",
            json={"notes": note},
            headers=reviewer_headers,
        )
        assert response.status_code == 200

    history = client.get(
        f"/api/requests/{request_id}/audit-history", headers=reviewer_headers
    ).json()

    assert [event["event_type"] for event in history] == [
        "NOTE_ADDED",
        "NOTE_UPDATED",
    ]
    assert [event["note"] for event in history] == [
        "Additional information required",
        "Information received",
    ]
    assert history[0]["id"] < history[1]["id"]


def test_audit_history_is_ordered_and_ignores_unchanged_values(client):
    user_headers = auth_headers(client, email="order-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="order-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, "Keep audit events ordered.")

    first = client.patch(
        f"/api/requests/{request_id}/triage",
        json={"status": "IN_REVIEW", "notes": "Review started"},
        headers=reviewer_headers,
    )
    unchanged = client.patch(
        f"/api/requests/{request_id}/triage",
        json={"status": "IN_REVIEW", "notes": "Review started"},
        headers=reviewer_headers,
    )
    final = client.patch(
        f"/api/requests/{request_id}/triage",
        json={"status": "APPROVED"},
        headers=reviewer_headers,
    )
    history = client.get(
        f"/api/requests/{request_id}/audit-history", headers=reviewer_headers
    ).json()

    assert first.status_code == unchanged.status_code == final.status_code == 200
    assert [event["event_type"] for event in history] == [
        "STATUS_CHANGED",
        "NOTE_ADDED",
        "STATUS_CHANGED",
    ]
    assert [event["new_status"] for event in history] == [
        "IN_REVIEW",
        None,
        "APPROVED",
    ]
    assert [event["id"] for event in history] == sorted(
        event["id"] for event in history
    )


def test_approval_queues_configured_external_handoff(client, monkeypatch):
    user_headers = auth_headers(client, email="handoff-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="handoff-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, "Send approved work downstream.")
    deliveries = []
    settings = SimpleNamespace(
        outbound_webhook_url="https://downstream.example.test/requests",
        outbound_webhook_timeout_seconds=3.0,
        outbound_webhook_secret="test-secret",
    )

    def capture_delivery(*args):
        deliveries.append(args)

    monkeypatch.setattr("app.api.routes.intake.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.routes.intake.deliver_approved_request_webhook", capture_delivery
    )

    response = client.patch(
        f"/api/requests/{request_id}/triage",
        json={"status": "APPROVED"},
        headers=reviewer_headers,
    )
    history = client.get(
        f"/api/requests/{request_id}/audit-history", headers=reviewer_headers
    ).json()

    assert response.status_code == 200
    assert response.json()["webhook_queued"] is True
    assert len(deliveries) == 1
    payload, url, timeout, secret = deliveries[0]
    assert payload["event"] == "request.approved"
    assert payload["request_id"] == request_id
    assert payload["status"] == "APPROVED"
    assert payload["approved_by_name"] == "Test User"
    assert url == settings.outbound_webhook_url
    assert timeout == 3.0
    assert secret == "test-secret"
    assert [event["event_type"] for event in history] == [
        "STATUS_CHANGED",
        "WEBHOOK_QUEUED",
    ]


def test_empty_audit_history_and_missing_request(client):
    user_headers = auth_headers(client, email="empty-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="empty-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, "No changes yet.")

    empty = client.get(
        f"/api/requests/{request_id}/audit-history", headers=reviewer_headers
    )
    missing = client.get(
        "/api/requests/999/audit-history", headers=reviewer_headers
    )

    assert empty.status_code == 200
    assert empty.json() == []
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Request not found: 999"


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
    brief = response.json()
    assert "Sales leaders" in brief["problem_summary"]
    assert brief["likely_users"] == ["Sales managers", "Sales operations analysts"]
    assert brief["solution_type"] == "Sales performance analytics dashboard"
    assert len(brief["clarifying_questions"]) == 2
    assert len(brief["risks"]) == 2
    assert brief["next_action"]

    stored = client.get(f"/api/requests/{request_id}", headers=user_headers)
    assert stored.status_code == 200
    assert stored.json()["request_text"] == raw_text

    db_override = client.app.dependency_overrides[get_db]
    db_generator = db_override()
    db = next(db_generator)
    try:
        generated = db.scalar(
            select(GeneratedBrief).where(GeneratedBrief.request_id == request_id)
        )
        assert generated is not None
        assert "Sales leaders" in generated.problem_summary
        assert generated.solution_type == "Sales performance analytics dashboard"
    finally:
        db_generator.close()


def test_mock_provider_returns_a_valid_structured_brief():
    brief = generate_structured_brief(
        "Automate manual customer onboarding approvals.", MockAIProvider()
    )

    assert brief.problem_summary
    assert brief.likely_users
    assert brief.solution_type == "Workflow automation"
    assert brief.clarifying_questions
    assert brief.risks
    assert brief.next_action


@pytest.mark.parametrize(
    ("request_text", "expected_solution_type"),
    [
        (
            "Employees struggle to compare health insurance plans during enrollment because coverage, costs, and benefits differ.",
            "Benefits comparison and decision-support portal",
        ),
        (
            "Sales managers combine separate Excel files every week to view performance against targets.",
            "Sales performance analytics dashboard",
        ),
        (
            "Customers repeatedly ask support agents about order status, delivery dates, refunds, and returns.",
            "Customer self-service and support automation",
        ),
        (
            "Finance manually extracts vendor invoice data from PDFs, scanned documents, and spreadsheets.",
            "Intelligent invoice processing automation",
        ),
        (
            "New employee onboarding activities span training, documentation, system access, and policy acknowledgements.",
            "Employee onboarding workflow and tracking",
        ),
        (
            "Employees email travel expenses and receipts while Finance tracks pending reimbursements manually.",
            "Travel expense workflow and reimbursement tracking",
        ),
        (
            "Employees request application access by email and IT must follow up for missing information.",
            "Application access request workflow",
        ),
        (
            "Marketing campaign data across email, social media, and search platforms is manually combined for performance reporting.",
            "Cross-channel marketing analytics dashboard",
        ),
        (
            "Facilities receives office issues about broken equipment, temperature, cleaning, and meeting rooms through different channels.",
            "Facilities service request management",
        ),
        (
            "Customer requests arrive through email, chat, spreadsheets, and different teams; management needs resolution and workload visibility.",
            "Omnichannel customer request management and analytics",
        ),
    ],
)
def test_mock_provider_classifies_mvp_examples(
    request_text: str, expected_solution_type: str
):
    brief = generate_structured_brief(request_text, MockAIProvider())

    assert brief.solution_type == expected_solution_type
    assert brief.problem_summary != request_text
    assert len(brief.clarifying_questions) >= 2
    assert len(brief.risks) >= 2


def test_ai_service_rejects_invalid_provider_output():
    class InvalidProvider:
        def generate_structured_brief(self, _: str) -> object:
            return {"problem_summary": "Missing required fields"}

    try:
        generate_structured_brief("Raw request", InvalidProvider())
    except AIOutputValidationError:
        pass
    else:
        raise AssertionError("Invalid provider output was not rejected")


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


def test_generate_brief_handles_invalid_ai_output(client, monkeypatch):
    user_headers = auth_headers(client, email="invalid-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="invalid-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, "Build an intake dashboard.")

    def invalid_output(_: str):
        raise AIOutputValidationError("invalid output")

    monkeypatch.setattr("app.api.routes.intake.generate_structured_brief", invalid_output)
    response = client.post(
        f"/api/requests/{request_id}/generate-brief", headers=reviewer_headers
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "AI provider returned invalid structured output"


def test_generate_brief_handles_provider_failure_without_changing_request(
    client, monkeypatch
):
    raw_text = "Automate a manual claims workflow."
    user_headers = auth_headers(client, email="failed-user@demo.io", role="USER")
    reviewer_headers = auth_headers(
        client, email="failed-reviewer@demo.io", role="REVIEWER"
    )
    request_id = create_request(client, user_headers, raw_text)

    def failed_generation(_: str):
        raise AIGenerationError("provider unavailable")

    monkeypatch.setattr("app.api.routes.intake.generate_structured_brief", failed_generation)
    response = client.post(
        f"/api/requests/{request_id}/generate-brief", headers=reviewer_headers
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "AI brief generation failed"
    stored = client.get(f"/api/requests/{request_id}", headers=user_headers)
    assert stored.json()["request_text"] == raw_text