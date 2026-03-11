"""Drop unused threshold_pct column from users table."""

import sqlalchemy as sa
from alembic import op

revision = "014_drop_threshold_pct"
down_revision = "013_cooldown_key_without_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_users_threshold_pct", "users", type_="check")
    op.drop_column("users", "threshold_pct")


def downgrade() -> None:
    op.add_column("users", sa.Column("threshold_pct", sa.Integer(), nullable=False, server_default="30"))
    op.create_check_constraint("ck_users_threshold_pct", "users", "threshold_pct BETWEEN 20 AND 50")
