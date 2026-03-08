"""Add support_tickets table

Revision ID: 006_add_support_tickets
Revises: 005_add_quiet_hours
Create Date: 2026-03-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_add_support_tickets"
down_revision: Union[str, None] = "005_add_quiet_hours"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=True),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("replied_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_tickets_user", "support_tickets", ["user_telegram_id"])


def downgrade() -> None:
    op.drop_index("ix_support_tickets_user", table_name="support_tickets")
    op.drop_table("support_tickets")
