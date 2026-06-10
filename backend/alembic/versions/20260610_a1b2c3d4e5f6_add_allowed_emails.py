"""add allowed_emails

Revision ID: a1b2c3d4e5f6
Revises: c3a1f8b2e45d
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "a1b2c3d4e5f6"
down_revision = "c3a1f8b2e45d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allowed_emails",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column(
            "added_by", UUID(as_uuid=True),
            sa.ForeignKey("parents.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_allowed_emails_email"),
    )


def downgrade() -> None:
    op.drop_table("allowed_emails")
