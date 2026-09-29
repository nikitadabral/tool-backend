from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.request import RequestRecord


class GeneratedBrief(Base):
    """Latest AI-generated structured brief for a business request."""

    __tablename__ = "generated_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    problem_summary: Mapped[str] = mapped_column(Text, nullable=False)
    likely_users: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    solution_type: Mapped[str] = mapped_column(String(255), nullable=False)
    clarifying_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    request: Mapped[RequestRecord] = relationship(back_populates="generated_brief")