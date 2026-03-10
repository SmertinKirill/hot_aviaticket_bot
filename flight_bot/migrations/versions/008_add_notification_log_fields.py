"""Add log fields to notifications table."""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("notifications", sa.Column("origin_iata", sa.String(10), nullable=True))
    op.add_column("notifications", sa.Column("dest_iata", sa.String(10), nullable=True))
    op.add_column("notifications", sa.Column("departure_at", sa.String(10), nullable=True))
    op.add_column("notifications", sa.Column("stops", sa.Integer(), nullable=True))
    op.add_column("notifications", sa.Column("ticket_link", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "ticket_link")
    op.drop_column("notifications", "stops")
    op.drop_column("notifications", "departure_at")
    op.drop_column("notifications", "dest_iata")
    op.drop_column("notifications", "origin_iata")
    op.drop_column("notifications", "telegram_id")
