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


# --- Начало: выбор города вылета ---

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполните /start")
        return
    await message.answer("Введите город вылета:")
    await state.set_state(SubscribeStates.waiting_for_origin_city)


@router.callback_query(F.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала выполните /start")
        return
    await callback.answer()
    await callback.message.edit_text("Введите город вылета:")
    await state.set_state(SubscribeStates.waiting_for_origin_city)


@router.message(SubscribeStates.waiting_for_origin_city)
async def process_origin_city_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    query = message.text.strip()
    cities = await search_cities(session, query)

    if not cities:
        await message.answer("Город не найден. Попробуйте ещё раз:")
        return

    if len(cities) == 1:
        city = cities[0]
        await state.update_data(origin_iata=city.iata)
        await state.set_state(None)
        await message.answer(
            f"Город вылета: {city.name_ru} ({city.iata})\n\nВыберите тип направления:",
            reply_markup=subscribe_type(),
        )
        return

    if len(cities) <= 8:
        kb = city_select([(c.iata, c.name_ru) for c in cities])
        for row in kb.inline_keyboard:
            for btn in row:
                iata = btn.callback_data.split(":")[1]
                btn.callback_data = f"sub_origin_pick:{iata}"
        await message.answer("Уточните город вылета:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много вариантов ({len(cities)}). Уточните запрос:"
    )


@router.callback_query(F.data.startswith("sub_origin_pick:"))
async def cb_origin_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    iata = callback.data.split(":")[1]
    await callback.answer()

    stmt = select(City.name_ru).where(City.iata == iata)
    result = await session.execute(stmt)
    city_name = result.scalar_one_or_none() or iata

    await state.update_data(origin_iata=iata)
    await state.set_state(None)
    await callback.message.edit_text(
        f"Город вылета: {city_name} ({iata})\n\nВыберите тип направления:",
        reply_markup=subscribe_type(),
    )


# --- Регион ---

@router.callback_query(F.data == "sub_region")
async def cb_sub_region(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Выберите регион:", reply_markup=region_select()
    )


@router.callback_query(F.data.startswith("region:"))
async def cb_region_select(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    region = callback.data.split(":", 1)[1]
    await callback.answer()

    data = await state.get_data()
    origin_iata = data.get("origin_iata")
    if not origin_iata:
        await callback.message.edit_text(
            "Сессия истекла. Начните заново с /subscribe"
        )
        return

    await _create_subscription(callback, state, session, origin_iata, "region", region)


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
        data = await state.get_data()
        origin_iata = data.get("origin_iata")
        if not origin_iata:
            await message.answer("Сессия истекла. Начните заново с /subscribe")
            await state.clear()
            return
        await state.clear()
        await _create_subscription_msg(message, session, origin_iata, "country", c.code)
        return

    if len(countries) <= 8:
        kb = country_select([(c.code, c.name_ru) for c in countries])
        for row in kb.inline_keyboard:
            for btn in row:
                code = btn.callback_data.split(":")[1]
                btn.callback_data = f"sub_country_pick:{code}"
        await state.set_state(None)
        await message.answer("Уточните страну:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много ({len(countries)}). Уточните запрос:"
    )


@router.callback_query(F.data.startswith("sub_country_pick:"))
async def cb_country_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    code = callback.data.split(":")[1]
    await callback.answer()

    data = await state.get_data()
    origin_iata = data.get("origin_iata")
    if not origin_iata:
        await callback.message.edit_text(
            "Сессия истекла. Начните заново с /subscribe"
        )
        return

    await _create_subscription(callback, state, session, origin_iata, "country", code)


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
        data = await state.get_data()
        origin_iata = data.get("origin_iata")
        if not origin_iata:
            await message.answer("Сессия истекла. Начните заново с /subscribe")
            await state.clear()
            return
        await state.clear()
        await _create_subscription_msg(message, session, origin_iata, "city", c.iata)
        return

    if len(cities) <= 8:
        kb = city_select([(c.iata, c.name_ru) for c in cities])
        for row in kb.inline_keyboard:
            for btn in row:
                iata = btn.callback_data.split(":")[1]
                btn.callback_data = f"sub_city_pick:{iata}"
        await state.set_state(None)
        await message.answer("Уточните город:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много ({len(cities)}). Уточните запрос:"
    )


@router.callback_query(F.data.startswith("sub_city_pick:"))
async def cb_city_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    iata = callback.data.split(":")[1]
    await callback.answer()

    data = await state.get_data()
    origin_iata = data.get("origin_iata")
    if not origin_iata:
        await callback.message.edit_text(
            "Сессия истекла. Начните заново с /subscribe"
        )
        return

    await _create_subscription(callback, state, session, origin_iata, "city", iata)


# --- Создание подписки ---

async def _create_subscription(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    origin_iata: str,
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
        await state.clear()
        await callback.message.edit_text(
            "У вас уже 10 подписок — это максимум. "
            "Удалите одну из существующих, чтобы добавить новую."
        )
        return

    try:
        await sub_repo.create(user.id, origin_iata, dest_type, dest_code)
    except IntegrityError:
        await session.rollback()
        await state.clear()
        await callback.message.edit_text(
            "Такая подписка у вас уже есть."
        )
        return

    await state.clear()
    label = await _dest_label(session, dest_type, dest_code)
    origin_name = await _city_name(session, origin_iata)
    await callback.message.edit_text(
        f"✅ Подписка добавлена: {origin_name} → {label}"
    )


async def _create_subscription_msg(
    message: Message,
    session: AsyncSession,
    origin_iata: str,
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
        await sub_repo.create(user.id, origin_iata, dest_type, dest_code)
    except IntegrityError:
        await session.rollback()
        await message.answer("Такая подписка у вас уже есть.")
        return

    label = await _dest_label(session, dest_type, dest_code)
    origin_name = await _city_name(session, origin_iata)
    await message.answer(f"✅ Подписка добавлена: {origin_name} → {label}")


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
        dest_label = await _dest_label(session, sub.dest_type, sub.dest_code)
        origin_name = await _city_name(session, sub.origin_iata)
        dest_labels[sub.id] = f"{origin_name} → {dest_label}"

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

    await _show_subscriptions(callback, session)


# --- Хелперы ---

async def _city_name(session: AsyncSession, iata: str) -> str:
    """Русское название города по IATA."""
    stmt = select(City.name_ru).where(City.iata == iata)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() or iata


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
