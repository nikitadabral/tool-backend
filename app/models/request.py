from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.generated_brief import GeneratedBrief


class RequestRecord(Base):
    """A submitted, unstructured business request."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_generation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING"
    )
    brief_generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requester_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    requester_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    generated_brief: Mapped[GeneratedBrief | None] = relationship(
        back_populates="request", cascade="all, delete-orphan", uselist=False
    )
