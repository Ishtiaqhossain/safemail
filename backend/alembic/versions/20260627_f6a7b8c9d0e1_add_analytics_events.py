"""add analytics_events

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("visitor_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("parent_id", UUID(as_uuid=True),
                  sa.ForeignKey("parents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("referrer", sa.String(), nullable=True),
        sa.Column("utm", JSONB(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="client"),
        sa.Column("properties", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analytics_events_name_created", "analytics_events", ["event_name", "created_at"])
    op.create_index("ix_analytics_events_visitor", "analytics_events", ["visitor_id"])
    op.create_index("ix_analytics_events_parent", "analytics_events", ["parent_id"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_created_at", table_name="analytics_events")
    op.drop_index("ix_analytics_events_parent", table_name="analytics_events")
    op.drop_index("ix_analytics_events_visitor", table_name="analytics_events")
    op.drop_index("ix_analytics_events_name_created", table_name="analytics_events")
    op.drop_table("analytics_events")
