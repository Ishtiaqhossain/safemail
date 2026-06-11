import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WaitlistEntry(Base):
    """An email captured from the public landing page requesting an invite.

    Distinct from AllowedEmail: a waitlist entry is just an expression of
    interest and grants no access. An admin reviews the list and promotes an
    entry to the allowlist (see app.routers.admin) to let that person register.

    Email is stored normalized (lowercase, trimmed) and uniquely constrained so
    repeated requests from the same address are idempotent.
    """
    __tablename__ = "waitlist_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
