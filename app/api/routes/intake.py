from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_reviewer
from app.db.session import get_db
from app.models.request import RequestRecord
from app.models.user import User
from app.schemas.brief import StructuredBrief
from app.schemas.intake import RequestCreate, RequestRead, TriageUpdate
from app.services.ai_service import generate_structured_brief

router = APIRouter(prefix="/api/requests", tags=["intake"])


@router.post("", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequestRecord:
    """Persist a new unstructured business request for the current user."""
    record = RequestRecord(
        request_text=payload.request_text,
        requester_id=current_user.id,
        requester_name=current_user.name,
    )
    db.add(record)
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
    return generate_structured_brief(record.request_text)


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


@router.patch("/{request_id}/triage", response_model=RequestRead)
def update_triage(
    request_id: int,
    payload: TriageUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_reviewer),
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
    if "status" in fields_set and payload.status is not None:
        record.status = payload.status.value
    if "priority" in fields_set:
        record.priority = payload.priority.value if payload.priority else None
    if "owner" in fields_set:
        record.owner = payload.owner.strip() if payload.owner else None
    if "notes" in fields_set:
        record.notes = payload.notes.strip() if payload.notes else None
    db.commit()
    db.refresh(record)
    return record
