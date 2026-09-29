from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RequestAuditRead(BaseModel):
    """An audit event returned to reviewer clients."""

    id: int
    request_id: int
    timestamp: datetime
    event_type: str
    previous_status: str | None = None
    new_status: str | None = None
    note: str | None = None
    reviewer_id: int | None = None
    reviewer_name: str | None = None

    model_config = ConfigDict(from_attributes=True)