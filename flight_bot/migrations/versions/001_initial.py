"""Initial migration

Revision ID: 001_initial
Revises:
Create Date: 2026-03-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- countries ---
    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name_ru", sa.String(), nullable=False),
        sa.Column("name_en", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # --- cities ---
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("iata", sa.String(), nullable=False),
        sa.Column("name_ru", sa.String(), nullable=False),
        sa.Column("name_en", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["country_code"], ["countries.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("iata"),
    )

    # --- airports ---
    op.create_table(
        "airports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("iata", sa.String(), nullable=False),
        sa.Column("name_ru", sa.String(), nullable=False),
        sa.Column("name_en", sa.String(), nullable=False),
        sa.Column("city_iata", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["city_iata"], ["cities.iata"]),
        sa.ForeignKeyConstraint(["country_code"], ["countries.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("iata"),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("origin_iata", sa.String(), nullable=True),
        sa.Column("threshold_pct", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "threshold_pct BETWEEN 20 AND 50", name="ck_users_threshold_pct"
        ),
        sa.ForeignKeyConstraint(["origin_iata"], ["cities.iata"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )

    # --- subscriptions ---
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dest_type", sa.String(), nullable=False),
        sa.Column("dest_code", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dest_type", "dest_code", name="uq_user_dest"),
    )

    # --- price_history ---
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("route_key", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("ticket_link", sa.String(), nullable=False),
        sa.Column(
            "found_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_price_history_route_found",
        "price_history",
        ["route_key", "found_at"],
    )

    # --- notifications ---
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("route_key", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Integer(), nullable=False),
        sa.Column("discount_pct", sa.Integer(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_sub_route_sent",
        "notifications",
        ["subscription_id", "route_key", "sent_at"],
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("price_history")
    op.drop_table("subscriptions")
    op.drop_table("users")
    op.drop_table("airports")
    op.drop_table("cities")
    op.drop_table("countries")
