"""Add currency to subscriptions."""

from alembic import op
import sqlalchemy as sa

revision = "010_add_currency"
down_revision = "009_drop_price_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "currency")
