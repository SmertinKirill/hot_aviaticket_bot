"""Drop price_history table."""

from alembic import op
import sqlalchemy as sa

revision = "009_drop_price_history"
down_revision = "008_add_notification_log_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("price_history")


def downgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("route_key", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("ticket_link", sa.String(), nullable=False),
        sa.Column("found_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_price_history_route_found", "price_history", ["route_key", "found_at"])
