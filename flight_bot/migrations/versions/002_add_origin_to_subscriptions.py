"""Add origin_iata to subscriptions

Revision ID: 002_add_origin_to_subscriptions
Revises: 001_initial
Create Date: 2026-03-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_origin_to_subscriptions"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем старый unique constraint
    op.drop_constraint("uq_user_dest", "subscriptions", type_="unique")

    # Очищаем существующие подписки — они невалидны без origin_iata
    op.execute("DELETE FROM subscriptions")

    # Добавляем колонку origin_iata (NOT NULL — таблица пустая)
    op.add_column(
        "subscriptions",
        sa.Column("origin_iata", sa.String(), nullable=False),
    )

    # FK на cities.iata
    op.create_foreign_key(
        "fk_subscriptions_origin_iata",
        "subscriptions",
        "cities",
        ["origin_iata"],
        ["iata"],
    )

    # Новый unique constraint включает origin_iata
    op.create_unique_constraint(
        "uq_user_origin_dest",
        "subscriptions",
        ["user_id", "origin_iata", "dest_type", "dest_code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_origin_dest", "subscriptions", type_="unique")
    op.drop_constraint(
        "fk_subscriptions_origin_iata", "subscriptions", type_="foreignkey"
    )
    op.drop_column("subscriptions", "origin_iata")
    op.create_unique_constraint(
        "uq_user_dest",
        "subscriptions",
        ["user_id", "dest_type", "dest_code"],
    )
