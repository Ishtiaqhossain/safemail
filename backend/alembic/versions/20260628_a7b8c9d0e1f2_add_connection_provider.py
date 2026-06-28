"""add provider column to gmail_connections

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default backfills existing rows to "google"; the column is the
    # discriminator for the email-provider abstraction.
    op.add_column(
        "gmail_connections",
        sa.Column("provider", sa.String(), nullable=False, server_default="google"),
    )


def downgrade() -> None:
    op.drop_column("gmail_connections", "provider")
