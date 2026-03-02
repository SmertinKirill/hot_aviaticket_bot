from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.db.models import Subscription, User


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_subscriptions(self, user_id: int) -> list[Subscription]:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.is_active.is_(True))
            .order_by(Subscription.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        origin_iata: str,
        dest_type: str,
        dest_code: str,
        date_from: date | None = None,
        date_to: date | None = None,
        max_stops: int | None = None,
        target_price: int | None = None,
    ) -> Subscription:
        # Если подписка уже есть (в т.ч. неактивная) — реактивируем её
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.origin_iata == origin_iata,
            Subscription.dest_type == dest_type,
            Subscription.dest_code == dest_code,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if existing.is_active:
                from sqlalchemy.exc import IntegrityError
                raise IntegrityError(None, None, Exception("duplicate active subscription"))
            existing.is_active = True
            existing.date_from = date_from
            existing.date_to = date_to
            existing.max_stops = max_stops
            existing.target_price = target_price
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        sub = Subscription(
            user_id=user_id,
            origin_iata=origin_iata,
            dest_type=dest_type,
            dest_code=dest_code,
            date_from=date_from,
            date_to=date_to,
            max_stops=max_stops,
            target_price=target_price,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def update(
        self,
        subscription_id: int,
        user_id: int,
        origin_iata: str,
        dest_type: str,
        dest_code: str,
        date_from: date | None = None,
        date_to: date | None = None,
        max_stops: int | None = None,
        target_price: int | None = None,
    ) -> bool:
        stmt = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.user_id == user_id,
            )
            .values(
                origin_iata=origin_iata,
                dest_type=dest_type,
                dest_code=dest_code,
                date_from=date_from,
                date_to=date_to,
                max_stops=max_stops,
                target_price=target_price,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def deactivate(self, subscription_id: int, user_id: int) -> bool:
        stmt = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.user_id == user_id,
            )
            .values(is_active=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def count_active(self, user_id: int) -> int:
        stmt = select(func.count()).where(
            Subscription.user_id == user_id, Subscription.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_all_active(self) -> list[Subscription]:
        stmt = (
            select(Subscription)
            .where(Subscription.is_active.is_(True))
            .options(joinedload(Subscription.user))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())
