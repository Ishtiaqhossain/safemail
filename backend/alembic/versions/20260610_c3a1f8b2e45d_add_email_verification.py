"""add_email_verification

Revision ID: c3a1f8b2e45d
Revises: 8beee9809d87
Create Date: 2026-06-10 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3a1f8b2e45d'
down_revision: Union[str, None] = '8beee9809d87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing accounts are treated as verified so they are not locked out.
    op.add_column('parents', sa.Column(
        'is_email_verified', sa.Boolean(), nullable=False, server_default='true'
    ))


def downgrade() -> None:
    op.drop_column('parents', 'is_email_verified')
