import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class GmailConnection(Base):
    __tablename__ = "gmail_connections"
    __table_args__ = (UniqueConstraint("child_id", "gmail_address"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    gmail_address: Mapped[str] = mapped_column(String, nullable=False)
    access_token: Mapped[str] = mapped_column(String, nullable=False)   # encrypted with Fernet
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)  # encrypted with Fernet
    token_expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    history_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # active | revoked | error
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship("Child", back_populates="gmail_connections")
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="gmail_connection")
