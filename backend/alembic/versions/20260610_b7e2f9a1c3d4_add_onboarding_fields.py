"""add onboarding fields to parents

Revision ID: b7e2f9a1c3d4
Revises: a1b2c3d4e5f6
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e2f9a1c3d4"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parents", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("parents", sa.Column("monitoring_consent_at", sa.DateTime(timezone=True), nullable=True))
    # Existing accounts predate onboarding — treat them as already onboarded so
    # they aren't forced through the wizard on next login.
    op.execute("UPDATE parents SET onboarding_completed_at = now() WHERE onboarding_completed_at IS NULL")


def downgrade() -> None:
    op.drop_column("parents", "monitoring_consent_at")
    op.drop_column("parents", "onboarding_completed_at")
