"""Add max_duration to subscriptions

Revision ID: 007_add_max_duration
Revises: 006_add_support_tickets
Create Date: 2026-03-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_add_max_duration"
down_revision: Union[str, None] = "006_add_support_tickets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("max_duration", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "max_duration")
