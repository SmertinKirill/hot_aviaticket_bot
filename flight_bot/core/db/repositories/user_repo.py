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

    async def update_threshold(self, user_id: int, threshold_pct: int) -> User:
        if not (20 <= threshold_pct <= 50):
            raise ValueError("Порог должен быть от 20 до 50%")
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(threshold_pct=threshold_pct)
            .returning(User)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one()
