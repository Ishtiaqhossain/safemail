import uuid
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parent: Mapped["Parent"] = relationship("Parent", back_populates="children")
    gmail_connections: Mapped[list["GmailConnection"]] = relationship("GmailConnection", back_populates="child", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="child", cascade="all, delete-orphan")
    alert_preference: Mapped["AlertPreference | None"] = relationship("AlertPreference", back_populates="child", uselist=False, cascade="all, delete-orphan")
    weekly_stats: Mapped[list["WeeklyStats"]] = relationship("WeeklyStats", back_populates="child", cascade="all, delete-orphan")
