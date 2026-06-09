import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    gmail_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gmail_connections.id"), nullable=False)
    gmail_message_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)          # inbound | outbound
    sender_address: Mapped[str] = mapped_column(String, nullable=False)
    recipient_addresses: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    subject_snippet: Mapped[str | None] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)           # critical | high | medium | low
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False)
    ai_response_script: Mapped[str | None] = mapped_column(Text)
    parent_feedback: Mapped[str | None] = mapped_column(String)             # correct | false_positive
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship("Child", back_populates="alerts")
    gmail_connection: Mapped["GmailConnection"] = relationship("GmailConnection", back_populates="alerts")
