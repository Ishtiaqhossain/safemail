import uuid
from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.database import Base


class AlertPreference(Base):
    __tablename__ = "alert_preferences"
    __table_args__ = (UniqueConstraint("parent_id", "child_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    disabled_categories: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    immediate_severities: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=lambda: ["critical", "high"])
    digest_frequency: Mapped[str] = mapped_column(Text, nullable=False, default="weekly")  # daily | weekly

    child: Mapped["Child"] = relationship("Child", back_populates="alert_preference")
