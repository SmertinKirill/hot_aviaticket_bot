"""Add max_stops and target_price to subscriptions

Revision ID: 004_add_stops_and_target_price
Revises: 003_add_dates_to_subscriptions
Create Date: 2026-03-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_add_stops_and_target_price"
down_revision: Union[str, None] = "003_add_dates_to_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("max_stops", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("target_price", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "target_price")
    op.drop_column("subscriptions", "max_stops")
