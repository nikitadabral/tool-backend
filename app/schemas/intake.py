from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Priority, RequestStatus
from app.schemas.brief import StructuredBrief


class RequestCreate(BaseModel):
    """Payload for submitting a new unstructured request."""

    request_text: str = Field(min_length=1, description="Free-form business request text.")


class TriageUpdate(BaseModel):
    """Reviewer-editable triage fields. Only fields provided are updated."""

    status: RequestStatus | None = None
    priority: Priority | None = None
    owner: str | None = None
    notes: str | None = None


class RequestRead(BaseModel):
    """A persisted request returned to clients."""

    id: int
    request_text: str
    status: str
    priority: str | None = None
    owner: str | None = None
    notes: str | None = None
    brief_generation_status: str
    brief_generation_error: str | None = None
    generated_brief: StructuredBrief | None = None
    requester_id: int | None = None
    requester_name: str | None = None
    created_at: datetime
    updated_at: datetime
    webhook_queued: bool = False

    model_config = ConfigDict(from_attributes=True)
