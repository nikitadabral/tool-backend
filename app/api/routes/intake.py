import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_reviewer
from app.config import get_settings
from app.core.enums import RequestStatus
from app.db.session import get_db
from app.models.generated_brief import GeneratedBrief
from app.models.request import RequestRecord
from app.models.request_audit import RequestAuditRecord
from app.models.user import User
from app.schemas.audit import RequestAuditRead
from app.schemas.brief import StructuredBrief
from app.schemas.intake import RequestCreate, RequestRead, TriageUpdate
from app.services.ai_service import (
    AIGenerationError,
    AIOutputValidationError,
    generate_structured_brief,
)
from app.services.webhook import deliver_approved_request_webhook

router = APIRouter(prefix="/api/requests", tags=["intake"])

_ACTIVE_REQUEST_STATUSES = {
    RequestStatus.NEW.value,
    RequestStatus.SUBMITTED.value,
    RequestStatus.IN_REVIEW.value,
    RequestStatus.APPROVED.value,
}


def _store_generated_brief(record: RequestRecord, db: Session) -> StructuredBrief:
    brief = generate_structured_brief(record.request_text)
    generated = record.generated_brief or GeneratedBrief(request_id=record.id)
    for field, value in brief.model_dump().items():
        setattr(generated, field, value)
    record.generated_brief = generated
    record.brief_generation_status = "SUCCEEDED"
    record.brief_generation_error = None
    db.add(generated)
    return brief


def _record_generation_failure(record: RequestRecord, message: str) -> None:
    record.brief_generation_status = "FAILED"
    record.brief_generation_error = message


def _parse_request_text(request_text: str) -> tuple[str, str]:
    title = ""
    body_lines: list[str] = []
    for line in request_text.splitlines():
        if line.startswith("Title: "):
            title = line.removeprefix("Title: ").strip()
        elif not line.startswith("Business area: "):
            body_lines.append(line)

    description = "\n".join(body_lines).strip()
    if not title:
        title = (description.splitlines()[0] if description else request_text).strip()
        title = title[:80] or "Untitled request"
    return title, description or request_text.strip()


def _normalize_request_description(request_text: str) -> str:
    _, description = _parse_request_text(request_text)
    return " ".join(description.casefold().split())


def _find_active_duplicate(
    request_text: str, requester_id: int, db: Session
) -> RequestRecord | None:
    normalized_description = _normalize_request_description(request_text)
    stmt = (
        select(RequestRecord)
        .where(
            RequestRecord.requester_id == requester_id,
            RequestRecord.status.in_(_ACTIVE_REQUEST_STATUSES),
        )
        .order_by(RequestRecord.id.desc())
    )
    return next(
        (
            record
            for record in db.scalars(stmt)
            if _normalize_request_description(record.request_text)
            == normalized_description
        ),
        None,
    )


@router.post("", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequestRecord:
    """Persist a new unstructured business request for the current user."""
    duplicate = _find_active_duplicate(payload.request_text, current_user.id, db)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Duplicate active request already exists: "
                f"#{duplicate.id} ({duplicate.status})"
            ),
        )

    record = RequestRecord(
        request_text=payload.request_text,
        requester_id=current_user.id,
        requester_name=current_user.name,
    )
    db.add(record)
    db.flush()
    try:
        _store_generated_brief(record, db)
    except AIOutputValidationError:
        _record_generation_failure(
            record, "AI provider returned invalid structured output"
        )
    except AIGenerationError:
        _record_generation_failure(record, "AI brief generation failed")
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[RequestRead])
def list_requests(
    db: Session = Depends(get_db),
    _: User = Depends(require_reviewer),
) -> list[RequestRecord]:
    """Return all submitted requests for the reviewer dashboard (REVIEWER only)."""
    stmt = select(RequestRecord).order_by(RequestRecord.created_at.desc())
    return list(db.scalars(stmt))


@router.get("/mine", response_model=list[RequestRead])
def list_my_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RequestRecord]:
    """Return the current user's submitted requests."""
    stmt = (
        select(RequestRecord)
        .where(RequestRecord.requester_id == current_user.id)
        .order_by(RequestRecord.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.get("/export/csv")
def export_requests_csv(
    db: Session = Depends(get_db),
    _: User = Depends(require_reviewer),
) -> Response:
    """Export every request with its latest persisted triage state."""
    records = list(db.scalars(select(RequestRecord).order_by(RequestRecord.id)))

    counters: dict[int | str, int] = {}
    request_numbers: dict[int, int] = {}
    for record in records:
        requester_key: int | str = (
            record.requester_id
            if record.requester_id is not None
            else record.requester_name or "unknown"
        )
        request_number = counters.get(requester_key, 0) + 1
        counters[requester_key] = request_number
        request_numbers[record.id] = request_number

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
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
    )
    for record in reversed(records):
        title, description = _parse_request_text(record.request_text)
        writer.writerow(
            [
                request_numbers[record.id],
                title,
                record.requester_name or "",
                description,
                record.owner or "",
                record.status,
                record.priority or "",
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="requests_export.csv"'
        },
    )


@router.post("/{request_id}/generate-brief", response_model=StructuredBrief)
def generate_request_brief(
    request_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_reviewer),
) -> StructuredBrief:
    """Generate a structured brief from the unchanged original request text."""
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request not found: {request_id}",
        )
    try:
        brief = _store_generated_brief(record, db)
    except AIOutputValidationError as exc:
        _record_generation_failure(
            record, "AI provider returned invalid structured output"
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider returned invalid structured output",
        ) from exc
    except AIGenerationError as exc:
        _record_generation_failure(record, "AI brief generation failed")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI brief generation failed",
        ) from exc

    db.commit()
    return brief


@router.get("/{request_id}", response_model=RequestRead)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> RequestRecord:
    """Return a single request by id."""
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request not found: {request_id}",
        )
    return record


@router.get("/{request_id}/audit-history", response_model=list[RequestAuditRead])
def get_request_audit_history(
    request_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_reviewer),
) -> list[RequestAuditRecord]:
    """Return a request's immutable reviewer history in chronological order."""
    if db.get(RequestRecord, request_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request not found: {request_id}",
        )
    stmt = (
        select(RequestAuditRecord)
        .where(RequestAuditRecord.request_id == request_id)
        .order_by(RequestAuditRecord.timestamp, RequestAuditRecord.id)
    )
    return list(db.scalars(stmt))


@router.patch("/{request_id}/triage", response_model=RequestRead)
def update_triage(
    request_id: int,
    payload: TriageUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
) -> RequestRecord:
    """Persist reviewer triage changes (REVIEWER only)."""
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request not found: {request_id}",
        )
    # Only apply fields the client explicitly sent, so a status-only edit does
    # not wipe existing priority/owner/notes.
    fields_set = payload.model_fields_set
    webhook_payload = None
    webhook_url = None
    if "status" in fields_set and payload.status is not None:
        new_status = payload.status.value
        if new_status != record.status:
            is_new_approval = new_status == RequestStatus.APPROVED.value
            db.add(
                RequestAuditRecord(
                    request_id=record.id,
                    event_type="STATUS_CHANGED",
                    previous_status=record.status,
                    new_status=new_status,
                    reviewer_id=current_user.id,
                    reviewer_name=current_user.name,
                )
            )
            record.status = new_status
            settings = get_settings()
            if is_new_approval and settings.outbound_webhook_url:
                webhook_url = settings.outbound_webhook_url
                webhook_payload = {
                    "event": "request.approved",
                    "request_id": record.id,
                    "request_text": record.request_text,
                    "requester_id": record.requester_id,
                    "requester_name": record.requester_name,
                    "status": new_status,
                    "priority": record.priority,
                    "owner": record.owner,
                    "approved_by_id": current_user.id,
                    "approved_by_name": current_user.name,
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                }
                db.add(
                    RequestAuditRecord(
                        request_id=record.id,
                        event_type="WEBHOOK_QUEUED",
                        note="Approved request queued for external handoff.",
                        reviewer_id=current_user.id,
                        reviewer_name=current_user.name,
                    )
                )
    if "priority" in fields_set:
        record.priority = payload.priority.value if payload.priority else None
    if "owner" in fields_set:
        record.owner = payload.owner.strip() if payload.owner else None
    if "notes" in fields_set:
        new_note = payload.notes.strip() if payload.notes else None
        if new_note != record.notes:
            db.add(
                RequestAuditRecord(
                    request_id=record.id,
                    event_type=("NOTE_ADDED" if record.notes is None else "NOTE_UPDATED"),
                    note=new_note,
                    reviewer_id=current_user.id,
                    reviewer_name=current_user.name,
                )
            )
            record.notes = new_note
    db.commit()
    db.refresh(record)
    record.webhook_queued = webhook_payload is not None
    if webhook_payload is not None and webhook_url is not None:
        settings = get_settings()
        background_tasks.add_task(
            deliver_approved_request_webhook,
            webhook_payload,
            webhook_url,
            settings.outbound_webhook_timeout_seconds,
            settings.outbound_webhook_secret,
        )
    return record
