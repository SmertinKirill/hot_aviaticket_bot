"""Онбординг: /start."""

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import add_first_subscription, main_menu
from core.db.models import Airport, City
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)

    if user:
        await message.answer(
            "С возвращением! Выберите действие:", reply_markup=main_menu()
        )
        return

    await user_repo.create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    await message.answer(
        "Привет! Я помогу найти горящие авиабилеты и уведомлю тебя, "
        "когда цена упадёт существенно ниже обычной.\n\n"
        "Добавьте первую подписку на направление:",
        reply_markup=add_first_subscription(),
    )


# Алиасы: популярные названия, которые пользователи вводят, но которые
# не совпадают точно с названием города в базе.
CITY_ALIASES: dict[str, str] = {
    "бали": "DPS",
}


async def search_cities(session: AsyncSession, query: str) -> list[City]:
    """Поиск городов по названию города и названиям аэропортов."""
    alias_iata = CITY_ALIASES.get(query.strip().lower())
    if alias_iata:
        stmt = select(City).where(City.iata == alias_iata)
        result = await session.execute(stmt)
        city = result.scalar_one_or_none()
        if city:
            return [city]

    stmt = select(City).where(
        (City.name_ru.ilike(f"%{query}%")) | (City.name_en.ilike(f"%{query}%"))
    )
    result = await session.execute(stmt)
    cities_by_name = result.scalars().all()

    stmt = (
        select(City)
        .join(Airport, Airport.city_iata == City.iata)
        .where(
            (Airport.name_ru.ilike(f"%{query}%"))
            | (Airport.name_en.ilike(f"%{query}%"))
        )
    )
    result = await session.execute(stmt)
    cities_by_airport = result.scalars().all()

    seen = set()
    cities = []
    for c in [*cities_by_name, *cities_by_airport]:
        if c.iata not in seen:
            seen.add(c.iata)
            cities.append(c)
    return cities
