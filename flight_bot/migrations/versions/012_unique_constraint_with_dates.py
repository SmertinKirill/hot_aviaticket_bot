"""Extend unique constraint on subscriptions to include dates."""

from alembic import op

revision = "012_unique_constraint_dates"
down_revision = "011_add_default_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_user_origin_dest", "subscriptions", type_="unique")
    op.create_unique_constraint(
        "uq_user_origin_dest",
        "subscriptions",
        ["user_id", "origin_iata", "dest_type", "dest_code", "date_from", "date_to"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_origin_dest", "subscriptions", type_="unique")
    op.create_unique_constraint(
        "uq_user_origin_dest",
        "subscriptions",
        ["user_id", "origin_iata", "dest_type", "dest_code"],
    )
