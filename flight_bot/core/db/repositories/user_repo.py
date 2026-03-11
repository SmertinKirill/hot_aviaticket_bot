from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, telegram_id: int, username: str | None) -> User:
        user = User(telegram_id=telegram_id, username=username)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_origin(self, user_id: int, origin_iata: str) -> User:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(origin_iata=origin_iata)
            .returning(User)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one()

    async def update_quiet_hours(
        self, user_id: int, quiet_from: int | None, quiet_to: int | None
    ) -> None:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(quiet_from=quiet_from, quiet_to=quiet_to)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_default_currency(self, user_id: int, currency: str) -> None:
        stmt = update(User).where(User.id == user_id).values(default_currency=currency)
        await self.session.execute(stmt)
        await self.session.commit()

