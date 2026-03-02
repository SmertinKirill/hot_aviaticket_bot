"""Онбординг: /start и выбор города вылета."""

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import add_first_subscription, city_select, main_menu
from bot.states import OnboardingStates
from core.db.models import Airport, City
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)

    if user and user.origin_iata:
        await message.answer(
            "С возвращением! Выберите действие:", reply_markup=main_menu()
        )
        return

    if not user:
        await user_repo.create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

    await message.answer(
        "Привет! Я помогу найти горящие авиабилеты и уведомлю тебя, "
        "когда цена упадёт существенно ниже обычной.\n\n"
        "Для начала — укажи свой город вылета:"
    )
    await state.set_state(OnboardingStates.waiting_for_city)


@router.message(OnboardingStates.waiting_for_city)
async def process_city_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    query = message.text.strip()
    await _search_and_select_city(
        message, state, session, query, is_onboarding=True
    )


async def search_cities(session: AsyncSession, query: str) -> list[City]:
    """Поиск городов по названию города и названиям аэропортов."""
    # Прямой поиск по городам
    stmt = select(City).where(
        (City.name_ru.ilike(f"%{query}%")) | (City.name_en.ilike(f"%{query}%"))
    )
    result = await session.execute(stmt)
    cities_by_name = result.scalars().all()

    # Поиск по названиям аэропортов → их города
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

    # Объединяем, убираем дубли, сохраняем порядок
    seen = set()
    cities = []
    for c in [*cities_by_name, *cities_by_airport]:
        if c.iata not in seen:
            seen.add(c.iata)
            cities.append(c)
    return cities


async def _search_and_select_city(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    query: str,
    is_onboarding: bool = True,
):
    """Общая логика поиска города."""
    cities = await search_cities(session, query)

    callback_prefix = "onboard_city" if is_onboarding else "setorigin_city"

    if not cities:
        await message.answer(
            "Город не найден. Попробуйте ввести название ещё раз:"
        )
        return

    if len(cities) == 1:
        city = cities[0]
        await _save_city(message, state, session, city.iata, is_onboarding)
        return

    if len(cities) <= 5:
        kb = city_select([(c.iata, c.name_ru) for c in cities])
        # Переписываем callback_data для правильного префикса
        for row in kb.inline_keyboard:
            for btn in row:
                iata = btn.callback_data.split(":")[1]
                btn.callback_data = f"{callback_prefix}:{iata}"
        await message.answer("Уточните город:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много вариантов ({len(cities)}). "
        "Уточните запрос:"
    )


async def _save_city(
    message_or_callback,
    state: FSMContext,
    session: AsyncSession,
    iata: str,
    is_onboarding: bool,
):
    """Сохранить выбранный город вылета."""
    user_repo = UserRepository(session)

    if isinstance(message_or_callback, CallbackQuery):
        tg_id = message_or_callback.from_user.id
    else:
        tg_id = message_or_callback.from_user.id

    user = await user_repo.get_by_telegram_id(tg_id)
    if not user:
        return

    await user_repo.update_origin(user.id, iata)
    await state.clear()

    # Получить название
    stmt = select(City.name_ru).where(City.iata == iata)
    result = await session.execute(stmt)
    city_name = result.scalar_one_or_none() or iata

    if is_onboarding:
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.edit_text(
                f"Отлично! Город вылета: {city_name} ({iata})\n\n"
                "Теперь добавьте первую подписку на направление:",
                reply_markup=add_first_subscription(),
            )
        else:
            await message_or_callback.answer(
                f"Отлично! Город вылета: {city_name} ({iata})\n\n"
                "Теперь добавьте первую подписку на направление:",
                reply_markup=add_first_subscription(),
            )
    else:
        text = f"Город вылета обновлён: {city_name} ({iata})"
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.edit_text(text)
        else:
            await message_or_callback.answer(text)


@router.callback_query(F.data.startswith("onboard_city:"))
async def on_onboard_city_select(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    iata = callback.data.split(":")[1]
    await callback.answer()
    await _save_city(callback, state, session, iata, is_onboarding=True)
