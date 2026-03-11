"""Add quiet_timezone to users

Revision ID: 015_add_quiet_timezone
Revises: 014_drop_threshold_pct
Create Date: 2026-03-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_add_quiet_timezone"
down_revision: Union[str, None] = "014_drop_threshold_pct"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("quiet_timezone", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quiet_timezone")
