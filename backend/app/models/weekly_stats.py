import uuid
from datetime import date
from sqlalchemy import ForeignKey, Integer, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class WeeklyStats(Base):
    __tablename__ = "weekly_stats"
    __table_args__ = (UniqueConstraint("child_id", "week_start"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    total_emails: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    emails_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alerts_by_severity: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    alerts_by_category: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    top_senders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    child: Mapped["Child"] = relationship("Child", back_populates="weekly_stats")
