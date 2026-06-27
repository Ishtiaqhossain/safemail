"""add health_incidents

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_incidents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("check_name", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("remediation_status", sa.String(), nullable=True),
        sa.Column("remediation", JSONB(), nullable=True),
        sa.Column("times_seen", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_health_incidents_fingerprint", "health_incidents", ["fingerprint"])
    op.create_index("ix_health_incidents_status", "health_incidents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_health_incidents_status", table_name="health_incidents")
    op.drop_index("ix_health_incidents_fingerprint", table_name="health_incidents")
    op.drop_table("health_incidents")
