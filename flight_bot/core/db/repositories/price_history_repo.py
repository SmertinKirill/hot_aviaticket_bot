from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import PriceHistory


class PriceHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self, route_key: str, price: int, ticket_link: str
    ) -> PriceHistory:
        record = PriceHistory(
            route_key=route_key, price=price, ticket_link=ticket_link
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_latest(self, route_key: str) -> PriceHistory | None:
        stmt = (
            select(PriceHistory)
            .where(PriceHistory.route_key == route_key)
            .order_by(PriceHistory.found_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_prefix(
        self,
        prefix: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PriceHistory | None:
        """Получить последнюю запись где route_key начинается с prefix.

        route_key формат: ORIGIN:DEST:YYYY-MM-DD — ISO-даты сортируются лексикографически,
        поэтому фильтрация строковым сравнением работает корректно.
        """
        stmt = select(PriceHistory).where(PriceHistory.route_key.like(f"{prefix}%"))
        if date_from:
            stmt = stmt.where(PriceHistory.route_key >= f"{prefix}{date_from.isoformat()}")
        if date_to:
            stmt = stmt.where(PriceHistory.route_key <= f"{prefix}{date_to.isoformat()}z")
        stmt = stmt.order_by(PriceHistory.found_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_avg_price(
        self, route_key: str, weeks: int = 8
    ) -> float | None:
        since = datetime.utcnow() - timedelta(weeks=weeks)
        stmt = select(func.avg(PriceHistory.price)).where(
            PriceHistory.route_key == route_key,
            PriceHistory.found_at >= since,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_count(self, route_key: str, weeks: int = 8) -> int:
        since = datetime.utcnow() - timedelta(weeks=weeks)
        stmt = select(func.count()).where(
            PriceHistory.route_key == route_key,
            PriceHistory.found_at >= since,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def delete_older_than(self, weeks: int) -> int:
        cutoff = datetime.utcnow() - timedelta(weeks=weeks)
        stmt = delete(PriceHistory).where(PriceHistory.found_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount
