import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class HealthIncident(Base):
    """A problem the self-monitoring system detected.

    One row per *distinct* active problem, keyed by ``fingerprint`` so a probe
    that keeps tripping every cycle updates the same open incident instead of
    creating duplicates. The remediation agent's diagnosis and the actions it
    took are written back onto the row.
    """

    __tablename__ = "health_incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Stable identity of the problem (e.g. "celery_queue_backlog" or
    # "stale_connection:<id>"). While an incident is open we dedup on this.
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    check_name: Mapped[str] = mapped_column(String, nullable=False)

    severity: Mapped[str] = mapped_column(String, nullable=False)   # info | warning | critical
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")  # open | resolved | acknowledged

    title: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSONB)   # the numbers that tripped the probe

    # Remediation agent output.
    diagnosis: Mapped[str | None] = mapped_column(Text)
    remediation_status: Mapped[str | None] = mapped_column(String)  # none | diagnosed | attempted | succeeded | failed | escalated
    remediation: Mapped[dict | None] = mapped_column(JSONB)         # {actions: [...], recommendation, mode}

    times_seen: Mapped[int] = mapped_column(default=1, nullable=False)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
