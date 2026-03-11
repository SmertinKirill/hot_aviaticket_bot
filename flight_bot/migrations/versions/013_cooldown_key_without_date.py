"""Strip departure date from notification route_keys for cooldown deduplication."""

from alembic import op

revision = "013_cooldown_key_without_date"
down_revision = "012_unique_constraint_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Обрезаем дату из route_key: "MOW:KUL:2026-04-01" → "MOW:KUL"
    op.execute(
        """
        UPDATE notifications
        SET route_key = split_part(route_key, ':', 1) || ':' || split_part(route_key, ':', 2)
        WHERE route_key LIKE '%:%:%'
        """
    )


def downgrade() -> None:
    # Восстановить исходные значения невозможно — дата потеряна
    pass
