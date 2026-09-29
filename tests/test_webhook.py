import hashlib
import hmac
import json

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.request import RequestRecord
from app.models.request_audit import RequestAuditRecord
from app.models.user import User
from app.services import webhook


def webhook_payload(request_id: int = 42, reviewer_id: int = 7):
    return {
        "event": "request.approved",
        "request_id": request_id,
        "request_text": "Automate an approval workflow.",
        "requester_id": 3,
        "requester_name": "Requester",
        "status": "APPROVED",
        "priority": "HIGH",
        "owner": "Reviewer",
        "approved_by_id": reviewer_id,
        "approved_by_name": "Reviewer",
        "approved_at": "2026-09-29T12:00:00+00:00",
    }


def test_webhook_sender_posts_json_with_hmac_signature():
    captured = {}

    def handler(request: httpx.Request):
        captured["body"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(202)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        webhook.send_approved_request_webhook(
            webhook_payload(),
            "https://downstream.example.test/requests",
            3.0,
            secret="shared-secret",
            client=client,
        )

    expected = hmac.new(
        b"shared-secret", captured["body"], hashlib.sha256
    ).hexdigest()
    assert json.loads(captured["body"])["event"] == "request.approved"
    assert captured["headers"]["x-webhook-event"] == "request.approved"
    assert captured["headers"]["x-webhook-signature"] == f"sha256={expected}"


def test_delivery_failure_is_recorded_without_raising(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as db:
        reviewer = User(
            name="Reviewer",
            email="reviewer@demo.io",
            password_hash="hash",
            role="REVIEWER",
        )
        request = RequestRecord(request_text="Test request", status="APPROVED")
        db.add_all([reviewer, request])
        db.commit()
        reviewer_id = reviewer.id
        request_id = request.id

    def fail_delivery(*_args, **_kwargs):
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(webhook, "send_approved_request_webhook", fail_delivery)

    webhook.deliver_approved_request_webhook(
        webhook_payload(request_id, reviewer_id),
        "https://downstream.example.test/requests",
        3.0,
        session_factory=TestingSessionLocal,
    )

    with TestingSessionLocal() as db:
        event = db.scalar(
            select(RequestAuditRecord).where(
                RequestAuditRecord.request_id == request_id
            )
        )
        assert event is not None
        assert event.event_type == "WEBHOOK_FAILED"
        assert event.note == "External handoff failed (ConnectError)."

    Base.metadata.drop_all(bind=engine)