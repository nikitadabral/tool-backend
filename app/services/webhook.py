import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.request_audit import RequestAuditRecord

logger = logging.getLogger(__name__)


def send_approved_request_webhook(
    payload: dict[str, Any],
    webhook_url: str,
    timeout_seconds: float,
    secret: str | None = None,
    client: httpx.Client | None = None,
) -> None:
    """Send one approved-request event and raise when delivery fails."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": "request.approved",
    }
    if secret:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={digest}"

    if client is not None:
        response = client.post(
            webhook_url, content=body, headers=headers, timeout=timeout_seconds
        )
        response.raise_for_status()
        return

    with httpx.Client(timeout=timeout_seconds) as owned_client:
        response = owned_client.post(webhook_url, content=body, headers=headers)
        response.raise_for_status()


def deliver_approved_request_webhook(
    payload: dict[str, Any],
    webhook_url: str,
    timeout_seconds: float,
    secret: str | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Deliver an approval event and record the outcome without raising."""
    target = urlsplit(webhook_url).netloc or "configured endpoint"
    try:
        send_approved_request_webhook(
            payload, webhook_url, timeout_seconds, secret=secret
        )
        event_type = "WEBHOOK_SENT"
        note = f"Approved request delivered to {target}."
    except Exception as exc:
        logger.warning(
            "Approved request webhook delivery failed for request %s: %s",
            payload["request_id"],
            type(exc).__name__,
        )
        event_type = "WEBHOOK_FAILED"
        note = f"External handoff failed ({type(exc).__name__})."

    db = session_factory()
    try:
        db.add(
            RequestAuditRecord(
                request_id=payload["request_id"],
                event_type=event_type,
                note=note,
                reviewer_id=payload["approved_by_id"],
                reviewer_name=payload["approved_by_name"],
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Could not record webhook outcome for request %s",
            payload["request_id"],
        )
    finally:
        db.close()