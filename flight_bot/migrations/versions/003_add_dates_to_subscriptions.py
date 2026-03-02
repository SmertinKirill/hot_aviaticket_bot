"""Add date_from and date_to to subscriptions

Revision ID: 003_add_dates_to_subscriptions
Revises: 002_add_origin_to_subscriptions
Create Date: 2026-03-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_dates_to_subscriptions"
down_revision: Union[str, None] = "002_add_origin_to_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("date_from", sa.Date(), nullable=True))
    op.add_column("subscriptions", sa.Column("date_to", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "date_to")
    op.drop_column("subscriptions", "date_from")
