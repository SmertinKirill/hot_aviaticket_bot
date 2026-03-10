"""Add default_currency to users."""

from alembic import op
import sqlalchemy as sa

revision = "011_add_default_currency"
down_revision = "010_add_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("default_currency", sa.String(3), nullable=False, server_default="RUB"),
    )


def downgrade() -> None:
    op.drop_column("users", "default_currency")
