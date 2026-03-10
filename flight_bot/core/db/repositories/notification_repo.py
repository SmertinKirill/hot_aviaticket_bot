from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_last(
        self, subscription_id: int, route_key: str
    ) -> Notification | None:
        stmt = (
            select(Notification)
            .where(
                Notification.subscription_id == subscription_id,
                Notification.route_key == route_key,
            )
            .order_by(Notification.sent_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        subscription_id: int,
        route_key: str,
        price: int,
        avg_price: int,
        discount_pct: int,
        telegram_id: int | None = None,
        origin_iata: str | None = None,
        dest_iata: str | None = None,
        departure_at: str | None = None,
        stops: int | None = None,
        ticket_link: str | None = None,
    ) -> Notification:
        notif = Notification(
            subscription_id=subscription_id,
            route_key=route_key,
            price=price,
            avg_price=avg_price,
            discount_pct=discount_pct,
            telegram_id=telegram_id,
            origin_iata=origin_iata,
            dest_iata=dest_iata,
            departure_at=departure_at,
            stops=stops,
            ticket_link=ticket_link,
        )
        self.session.add(notif)
        await self.session.commit()
        await self.session.refresh(notif)
        return notif
