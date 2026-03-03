"""Add quiet hours to users

Revision ID: 005_add_quiet_hours
Revises: 004_add_stops_and_target_price
Create Date: 2026-03-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_add_quiet_hours"
down_revision: Union[str, None] = "004_add_stops_and_target_price"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("quiet_from", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("quiet_to", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quiet_to")
    op.drop_column("users", "quiet_from")
