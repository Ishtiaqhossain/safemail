import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AnalyticsEvent(Base):
    """A single first-party product-analytics event.

    Privacy by design: we never store IP addresses, raw email, or any PII in
    events. Identity is an anonymous, client-generated ``visitor_id`` before
    login; once a parent is known the row is stitched to ``parent_id`` (a UUID
    FK, not an email). Dynamic data lives in ``properties`` (JSONB), never in the
    ``event_name`` — names are fixed, allowlisted strings (see
    app/services/analytics_events.py).
    """

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_name_created", "event_name", "created_at"),
        Index("ix_analytics_events_visitor", "visitor_id"),
        Index("ix_analytics_events_parent", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    event_name: Mapped[str] = mapped_column(String, nullable=False)          # object_action, allowlisted
    visitor_id: Mapped[str] = mapped_column(String, nullable=False)          # anonymous first-party id
    session_id: Mapped[str | None] = mapped_column(String)                   # per-session id
    # Set when the actor is a known parent (client token or server-side event).
    # ON DELETE CASCADE so a parent's events are erased with their account —
    # the product promises a full hard-delete, and that must reach analytics.
    # Pre-login anonymous events (parent_id NULL) carry no PII and are retained.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parents.id", ondelete="CASCADE")
    )

    # Page/marketing context (client events). No PII.
    path: Mapped[str | None] = mapped_column(String)
    referrer: Mapped[str | None] = mapped_column(String)
    utm: Mapped[dict | None] = mapped_column(JSONB)                          # {source, medium, campaign}

    # Where the event was recorded: "client" (browser) or "server" (authoritative).
    source: Mapped[str] = mapped_column(String, nullable=False, default="client")
    properties: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
