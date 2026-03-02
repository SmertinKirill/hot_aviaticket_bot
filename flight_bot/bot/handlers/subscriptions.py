"""Хендлеры подписок: /subscribe, /mysubscriptions, /unsubscribe."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from bot.handlers.start import search_cities
from bot.keyboards.inline import (
    city_select,
    country_select,
    region_select,
    subscribe_type,
    subscription_list,
)
from bot.states import SubscribeStates
from core.db.models import City, Country
from core.db.repositories.subscription_repo import SubscriptionRepository
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)

REGIONS = {
    "ЮВА": "ЮВА",
    "Европа": "Европа",
    "ОАЭ и Ближний Восток": "ОАЭ и Ближний Восток",
}


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user or not user.origin_iata:
        await message.answer(
            "Сначала укажите город вылета командой /start"
        )
        return
    await message.answer(
        "Выберите тип направления:", reply_markup=subscribe_type()
    )


@router.callback_query(F.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user or not user.origin_iata:
        await callback.answer("Сначала укажите город вылета командой /start")
        return
    await callback.answer()
    await callback.message.edit_text(
        "Выберите тип направления:", reply_markup=subscribe_type()
    )


# --- Регион ---

@router.callback_query(F.data == "sub_region")
async def cb_sub_region(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Выберите регион:", reply_markup=region_select()
    )


@router.callback_query(F.data.startswith("region:"))
async def cb_region_select(callback: CallbackQuery, session: AsyncSession):
    region = callback.data.split(":", 1)[1]
    await callback.answer()
    await _create_subscription(callback, session, "region", region)


# --- Страна ---

@router.callback_query(F.data == "sub_country")
async def cb_sub_country(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Введите название страны:")
    await state.set_state(SubscribeStates.waiting_for_country_input)


@router.message(SubscribeStates.waiting_for_country_input)
async def process_country_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    query = message.text.strip()
    stmt = select(Country).where(
        (Country.name_ru.ilike(f"%{query}%"))
        | (Country.name_en.ilike(f"%{query}%"))
    )
    result = await session.execute(stmt)
    countries = result.scalars().all()

    if not countries:
        await message.answer("Страна не найдена. Попробуйте ещё раз:")
        return

    if len(countries) == 1:
        c = countries[0]
        await state.clear()
        await _create_subscription_msg(message, session, "country", c.code)
        return

    if len(countries) <= 5:
        kb = country_select([(c.code, c.name_ru) for c in countries])
        # Меняем callback на sub_country_pick
        for row in kb.inline_keyboard:
            for btn in row:
                code = btn.callback_data.split(":")[1]
                btn.callback_data = f"sub_country_pick:{code}"
        await state.clear()
        await message.answer("Уточните страну:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много ({len(countries)}). Уточните запрос:"
    )


@router.callback_query(F.data.startswith("sub_country_pick:"))
async def cb_country_pick(callback: CallbackQuery, session: AsyncSession):
    code = callback.data.split(":")[1]
    await callback.answer()
    await _create_subscription(callback, session, "country", code)


# --- Город ---

@router.callback_query(F.data == "sub_city")
async def cb_sub_city(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Введите название города назначения:")
    await state.set_state(SubscribeStates.waiting_for_city_input)


@router.message(SubscribeStates.waiting_for_city_input)
async def process_city_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    query = message.text.strip()
    cities = await search_cities(session, query)

    if not cities:
        await message.answer("Город не найден. Попробуйте ещё раз:")
        return

    if len(cities) == 1:
        c = cities[0]
        await state.clear()
        await _create_subscription_msg(message, session, "city", c.iata)
        return

    if len(cities) <= 5:
        kb = city_select([(c.iata, c.name_ru) for c in cities])
        for row in kb.inline_keyboard:
            for btn in row:
                iata = btn.callback_data.split(":")[1]
                btn.callback_data = f"sub_city_pick:{iata}"
        await state.clear()
        await message.answer("Уточните город:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много ({len(cities)}). Уточните запрос:"
    )


@router.callback_query(F.data.startswith("sub_city_pick:"))
async def cb_city_pick(callback: CallbackQuery, session: AsyncSession):
    iata = callback.data.split(":")[1]
    await callback.answer()
    await _create_subscription(callback, session, "city", iata)


# --- Создание подписки ---

async def _create_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    dest_type: str,
    dest_code: str,
):
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    count = await sub_repo.count_active(user.id)
    if count >= 10:
        await callback.message.edit_text(
            "У вас уже 10 подписок — это максимум. "
            "Удалите одну из существующих, чтобы добавить новую."
        )
        return

    try:
        await sub_repo.create(user.id, dest_type, dest_code)
    except IntegrityError:
        await session.rollback()
        await callback.message.edit_text(
            "Такая подписка у вас уже есть."
        )
        return

    label = await _dest_label(session, dest_type, dest_code)
    await callback.message.edit_text(f"✅ Подписка добавлена: {label}")


async def _create_subscription_msg(
    message: Message,
    session: AsyncSession,
    dest_type: str,
    dest_code: str,
):
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        return

    count = await sub_repo.count_active(user.id)
    if count >= 10:
        await message.answer(
            "У вас уже 10 подписок — это максимум. "
            "Удалите одну из существующих, чтобы добавить новую."
        )
        return

    try:
        await sub_repo.create(user.id, dest_type, dest_code)
    except IntegrityError:
        await session.rollback()
        await message.answer("Такая подписка у вас уже есть.")
        return

    label = await _dest_label(session, dest_type, dest_code)
    await message.answer(f"✅ Подписка добавлена: {label}")


# --- Список подписок ---

@router.message(Command("mysubscriptions"))
async def cmd_my_subscriptions(message: Message, session: AsyncSession):
    await _show_subscriptions(message, session)


@router.callback_query(F.data == "my_subs")
async def cb_my_subscriptions(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    await _show_subscriptions(callback, session)


async def _show_subscriptions(
    event: Message | CallbackQuery, session: AsyncSession
):
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    tg_id = event.from_user.id
    user = await user_repo.get_by_telegram_id(tg_id)
    if not user:
        text = "Сначала выполните /start"
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
        else:
            await event.answer(text)
        return

    subs = await sub_repo.get_user_subscriptions(user.id)
    count = len(subs)

    if count == 0:
        text = "У вас пока нет подписок. Используйте /subscribe для добавления."
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
        else:
            await event.answer(text)
        return

    dest_labels = {}
    for sub in subs:
        dest_labels[sub.id] = await _dest_label(session, sub.dest_type, sub.dest_code)

    text = f"Твои подписки ({count}/10):"
    kb = subscription_list(subs, dest_labels)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


# --- Удаление подписки ---

@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, session: AsyncSession):
    await _show_subscriptions(message, session)


@router.callback_query(F.data.startswith("unsub:"))
async def cb_unsub(callback: CallbackQuery, session: AsyncSession):
    sub_id = int(callback.data.split(":")[1])
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    success = await sub_repo.deactivate(sub_id, user.id)
    if success:
        await callback.answer("Подписка удалена")
    else:
        await callback.answer("Подписка не найдена")

    # Обновить список
    await _show_subscriptions(callback, session)


# --- Хелперы ---

async def _dest_label(
    session: AsyncSession, dest_type: str, dest_code: str
) -> str:
    """Человекочитаемое название направления."""
    if dest_type == "region":
        return dest_code

    if dest_type == "country":
        stmt = select(Country.name_ru).where(Country.code == dest_code)
        result = await session.execute(stmt)
        name = result.scalar_one_or_none()
        return name or dest_code

    if dest_type == "city":
        stmt = select(City.name_ru).where(City.iata == dest_code)
        result = await session.execute(stmt)
        name = result.scalar_one_or_none()
        return f"{name or dest_code} ({dest_code})"

    return dest_code
