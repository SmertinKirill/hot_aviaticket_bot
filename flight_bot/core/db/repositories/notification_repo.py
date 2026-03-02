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
    ) -> Notification:
        notif = Notification(
            subscription_id=subscription_id,
            route_key=route_key,
            price=price,
            avg_price=avg_price,
            discount_pct=discount_pct,
        )
        self.session.add(notif)
        await self.session.commit()
        await self.session.refresh(notif)
        return notif
