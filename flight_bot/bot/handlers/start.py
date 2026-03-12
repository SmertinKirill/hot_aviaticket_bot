"""Онбординг: /start."""

import difflib
import logging
import re

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import add_first_subscription, main_menu
from core.db.models import Airport, City
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()

    # Убираем reply-клавиатуру если она осталась от предыдущего шага
    tmp = await message.answer("…", reply_markup=ReplyKeyboardRemove())
    await tmp.delete()

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
        "Привет! Я помогу найти горячие авиабилеты и уведомлю тебя, "
        "когда цена упадёт существенно ниже обычной.\n\n"
        "Добавьте первую подписку на направление:",
        reply_markup=add_first_subscription(),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Выберите действие:", reply_markup=main_menu())


# Алиасы: всё что пользователи вводят вместо официального названия города.
# Ключи — в нижнем регистре. Значения — IATA-код города.
CITY_ALIASES: dict[str, str] = {
    # Разговорные названия (кириллица)
    "бали": "DPS",
    "питер": "LED",
    "мск": "MOW",
    "екб": "SVX",
    "нск": "OVB",
    "крд": "KRR",
    "новосиб": "OVB",
    "сочи": "AER",
    "владик": "VVO",
    "хаб": "KHV",
    # IATA-коды (пользователи часто знают код)
    "led": "LED",
    "mow": "MOW",
    "svo": "MOW",
    "dme": "MOW",
    "vko": "MOW",
    "ovb": "OVB",
    "svx": "SVX",
    "krr": "KRR",
    "aer": "AER",
    "dps": "DPS",
    "bkk": "BKK",
    "dxb": "DXB",
    "ist": "IST",
    "hkt": "HKT",
    "kul": "KUL",
    "sin": "SIN",
    "tbs": "TBS",
    "evn": "EVN",
    "ala": "ALA",
    "tse": "NQZ",
    "cgk": "CGK",
    "cmb": "CMB",
    "bom": "BOM",
    "del": "DEL",
    "pek": "BJS",
    "pvg": "SHA",
    "nrt": "TYO",
    "icn": "SEL",
    "hnd": "TYO",
}


def _normalize_query(query: str) -> str:
    """Нормализовать запрос: нижний регистр, пробел вместо дефиса."""
    return query.strip().lower().replace("-", " ")


async def search_cities(session: AsyncSession, query: str) -> list[City]:
    """Поиск городов по названию города и названиям аэропортов."""
    normalized = _normalize_query(query)

    # 1. Алиасы (никнеймы, IATA-коды, сокращения)
    alias_iata = CITY_ALIASES.get(normalized) or CITY_ALIASES.get(query.strip().lower())
    if alias_iata:
        stmt = select(City).where(City.iata == alias_iata)
        result = await session.execute(stmt)
        city = result.scalar_one_or_none()
        if city:
            return [city]

    # 2. Поиск с нормализацией пробел/дефис
    queries = {query, normalized, query.strip().lower().replace(" ", "-")}

    conditions = []
    for q in queries:
        conditions += [
            City.name_ru.ilike(f"%{q}%"),
            City.name_en.ilike(f"%{q}%"),
        ]

    stmt = select(City).where(or_(*conditions))
    result = await session.execute(stmt)
    cities_by_name = result.scalars().all()

    # 3. Поиск по аэропортам
    airport_conditions = []
    for q in queries:
        airport_conditions += [
            Airport.name_ru.ilike(f"%{q}%"),
            Airport.name_en.ilike(f"%{q}%"),
        ]

    stmt = (
        select(City)
        .join(Airport, Airport.city_iata == City.iata)
        .where(or_(*airport_conditions))
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


async def suggest_cities(session: AsyncSession, query: str) -> list[City]:
    """Нечёткий поиск когда точный поиск не дал результатов.

    Стратегии:
    1. Префикс каждого слова (для "Санкт-Питербург" → "Санкт%")
    2. Короткий префикс всего запроса (для "Бангок" → "Банг%")
    Результаты ранжируются по сходству через difflib.
    """
    words = re.split(r"[\s\-]+", query.strip())
    short_prefix = query[:max(3, len(query) - 2)]

    patterns: set[str] = set()
    for word in words:
        if len(word) >= 3:
            patterns.add(f"{word}%")
    if len(short_prefix) >= 3:
        patterns.add(f"{short_prefix}%")

    if not patterns:
        return []

    conditions = [City.name_ru.ilike(p) for p in patterns]
    stmt = select(City).where(or_(*conditions)).limit(20)
    result = await session.execute(stmt)
    candidates = list(result.scalars().all())

    if not candidates:
        return []

    seen: set[str] = set()
    unique = []
    for c in candidates:
        if c.iata not in seen:
            seen.add(c.iata)
            unique.append(c)

    scored = sorted(
        unique,
        key=lambda c: difflib.SequenceMatcher(None, query.lower(), c.name_ru.lower()).ratio(),
        reverse=True,
    )
    return scored[:5]
