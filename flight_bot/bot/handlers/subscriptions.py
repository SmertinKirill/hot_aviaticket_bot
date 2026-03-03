"""Хендлеры подписок: /subscribe, /mysubscriptions, /unsubscribe."""

import logging
from calendar import monthrange
from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, KeyboardButton, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from bot.handlers.start import search_cities
from bot.keyboards.inline import (
    city_select,
    country_select,
    date_type_select,
    month_select,
    region_select,
    stops_select,
    subscribe_type,
    subscription_list,
)
from bot.states import SubscribeStates
from core.api.travelpayouts import get_cheap_tickets, get_global_min_price
from core.db.models import City, Country
from core.db.repositories.subscription_repo import SubscriptionRepository
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)

MONTHS_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
MONTHS_NOM = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель",
    5: "май", 6: "июнь", 7: "июль", 8: "август",
    9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}
STOPS_LABELS = {0: "только прямые", 1: "до 1 пересадки", 2: "до 2 пересадок"}

# Регионы (дублируем здесь для вычисления reference price)
_REGIONS = {
    "ЮВА": ["TH", "VN", "ID", "MY", "SG", "PH", "KH", "MM", "LA"],
    "ОАЭ и Ближний Восток": ["AE", "QA", "JO", "LB", "BH", "KW", "OM", "SA"],
    "Европа": ["DE", "FR", "IT", "ES", "CZ", "AT", "NL", "PL", "GR", "HR",
               "PT", "HU", "RO", "BG", "RS", "ME", "AL", "MK", "TR", "GE", "AM"],
    "Море": [
        "TR", "CY", "EG", "TN", "MA",
        "GR", "HR", "ME", "BG",
        "TH", "ID", "MV", "LK",
    ],
}


_POPULAR_ORIGINS = [
    "Москва", "Санкт-Петербург", "Казань",
    "Новосибирск", "Сочи", "Красноярск",
]


def _origin_reply_kb() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=city) for city in _POPULAR_ORIGINS[:3]],
        [KeyboardButton(text=city) for city in _POPULAR_ORIGINS[3:]],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)


# --- Начало: выбор города вылета ---

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполните /start")
        return
    logger.info("user_id=%d: начало создания подписки", message.from_user.id)
    await message.answer(
        "Введите полное название города вылета на русском:",
        reply_markup=_origin_reply_kb(),
    )
    await state.set_state(SubscribeStates.waiting_for_origin_city)


@router.callback_query(F.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Сначала выполните /start")
        return
    await callback.answer()
    await callback.message.edit_text("Выбор города вылета:")
    await callback.message.answer(
        "Введите полное название города вылета на русском:",
        reply_markup=_origin_reply_kb(),
    )
    await state.set_state(SubscribeStates.waiting_for_origin_city)


@router.message(SubscribeStates.waiting_for_origin_city, ~F.text.startswith("/"))
async def process_origin_city_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    query = message.text.strip()
    cities = await search_cities(session, query)

    if not cities:
        logger.info("user_id=%d: город вылета не найден, запрос=%r", message.from_user.id, query)
        await message.answer("Город не найден. Попробуйте ещё раз:")
        return

    remove_kb = ReplyKeyboardRemove()

    if len(cities) == 1:
        city = cities[0]
        await state.update_data(origin_iata=city.iata)
        await state.set_state(None)
        logger.info("user_id=%d: origin=%s", message.from_user.id, city.iata)
        await message.answer(
            f"Город вылета: {city.name_ru} ({city.iata})\n\nВыберите тип направления:",
            reply_markup=remove_kb,
        )
        await message.answer("Куда летим?", reply_markup=subscribe_type())
        return

    if len(cities) <= 8:
        kb = city_select([(c.iata, c.name_ru) for c in cities])
        for row in kb.inline_keyboard:
            for btn in row:
                iata = btn.callback_data.split(":")[1]
                btn.callback_data = f"sub_origin_pick:{iata}"
        await message.answer("Уточните город вылета:", reply_markup=remove_kb)
        await message.answer("Уточните город:", reply_markup=kb)
        return

    await message.answer(
        f"Найдено слишком много ({len(cities)}). Уточните запрос:",
        reply_markup=remove_kb,
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
    await callback.message.edit_text("Выберите регион:", reply_markup=region_select())


@router.callback_query(F.data.startswith("region:"))
async def cb_region_select(callback: CallbackQuery, state: FSMContext):
    region = callback.data.split(":", 1)[1]
    await callback.answer()
    data = await state.get_data()
    if not data.get("origin_iata"):
        await callback.message.edit_text("Сессия истекла. Начните заново с /subscribe")
        return
    await state.update_data(pending_dest_type="region", pending_dest_code=region)
    await callback.message.edit_text(
        "Выберите период вылета:", reply_markup=date_type_select()
    )


# --- Страна ---

@router.callback_query(F.data == "sub_country")
async def cb_sub_country(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Введите название страны:")
    await state.set_state(SubscribeStates.waiting_for_country_input)


@router.message(SubscribeStates.waiting_for_country_input, ~F.text.startswith("/"))
async def process_country_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    stmt = select(Country).where(
        (Country.name_ru.ilike(f"%{message.text.strip()}%"))
        | (Country.name_en.ilike(f"%{message.text.strip()}%"))
    )
    result = await session.execute(stmt)
    countries = result.scalars().all()

    if not countries:
        await message.answer("Страна не найдена. Попробуйте ещё раз:")
        return

    if len(countries) == 1:
        data = await state.get_data()
        if not data.get("origin_iata"):
            await message.answer("Сессия истекла. Начните заново с /subscribe")
            await state.clear()
            return
        await state.update_data(pending_dest_type="country", pending_dest_code=countries[0].code)
        await state.set_state(None)
        await message.answer("Выберите период вылета:", reply_markup=date_type_select())
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

    await message.answer(f"Найдено слишком много ({len(countries)}). Уточните запрос:")


@router.callback_query(F.data.startswith("sub_country_pick:"))
async def cb_country_pick(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    await callback.answer()
    data = await state.get_data()
    if not data.get("origin_iata"):
        await callback.message.edit_text("Сессия истекла. Начните заново с /subscribe")
        return
    await state.update_data(pending_dest_type="country", pending_dest_code=code)
    await callback.message.edit_text(
        "Выберите период вылета:", reply_markup=date_type_select()
    )


# --- Город ---

@router.callback_query(F.data == "sub_city")
async def cb_sub_city(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Введите название города назначения:")
    await state.set_state(SubscribeStates.waiting_for_city_input)


@router.message(SubscribeStates.waiting_for_city_input, ~F.text.startswith("/"))
async def process_city_input(
    message: Message, state: FSMContext, session: AsyncSession
):
    cities = await search_cities(session, message.text.strip())

    if not cities:
        await message.answer("Город не найден. Попробуйте ещё раз:")
        return

    if len(cities) == 1:
        data = await state.get_data()
        if not data.get("origin_iata"):
            await message.answer("Сессия истекла. Начните заново с /subscribe")
            await state.clear()
            return
        await state.update_data(pending_dest_type="city", pending_dest_code=cities[0].iata)
        await state.set_state(None)
        await message.answer("Выберите период вылета:", reply_markup=date_type_select())
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

    await message.answer(f"Найдено слишком много ({len(cities)}). Уточните запрос:")


@router.callback_query(F.data.startswith("sub_city_pick:"))
async def cb_city_pick(callback: CallbackQuery, state: FSMContext):
    iata = callback.data.split(":")[1]
    await callback.answer()
    data = await state.get_data()
    if not data.get("origin_iata"):
        await callback.message.edit_text("Сессия истекла. Начните заново с /subscribe")
        return
    await state.update_data(pending_dest_type="city", pending_dest_code=iata)
    await callback.message.edit_text(
        "Выберите период вылета:", reply_markup=date_type_select()
    )


# --- Выбор даты ---

@router.callback_query(F.data.startswith("date_type:"))
async def cb_date_type(callback: CallbackQuery, state: FSMContext):
    dtype = callback.data.split(":")[1]
    await callback.answer()

    if dtype == "any":
        await state.update_data(date_from=None, date_to=None)
        await state.set_state(None)
        await callback.message.edit_text(
            "Количество пересадок:", reply_markup=stops_select()
        )
        return

    if dtype == "month":
        await callback.message.edit_text("Выберите месяц:", reply_markup=month_select())
        return

    if dtype == "specific":
        await state.update_data(date_input_type="specific")
        await state.set_state(SubscribeStates.waiting_for_date_input)
        await callback.message.edit_text(
            "Введите дату в формате ДД.ММ.ГГГГ:\n(например: 15.04.2026)"
        )
        return

    if dtype == "range":
        await state.update_data(date_input_type="range")
        await state.set_state(SubscribeStates.waiting_for_date_input)
        await callback.message.edit_text(
            "Введите диапазон в формате ДД.ММ.ГГГГ - ДД.ММ.ГГГГ:\n"
            "(например: 01.04.2026 - 30.04.2026)"
        )
        return


@router.callback_query(F.data.startswith("date_month:"))
async def cb_date_month(callback: CallbackQuery, state: FSMContext):
    year_month = callback.data.split(":")[1]
    year, month = map(int, year_month.split("-"))
    last_day = monthrange(year, month)[1]
    await state.update_data(
        date_from=date(year, month, 1).isoformat(),
        date_to=date(year, month, last_day).isoformat(),
    )
    await state.set_state(None)
    await callback.answer()
    await callback.message.edit_text(
        "Количество пересадок:", reply_markup=stops_select()
    )


@router.message(SubscribeStates.waiting_for_date_input, ~F.text.startswith("/"))
async def process_date_input(message: Message, state: FSMContext):
    data = await state.get_data()
    text = message.text.strip()

    if data.get("date_input_type") == "specific":
        d = _parse_single_date(text)
        if not d:
            await message.answer("Неверный формат. Введите дату в формате ДД.ММ.ГГГГ:")
            return
        if d < date.today():
            await message.answer("Дата уже прошла. Введите дату в будущем:")
            return
        await state.update_data(date_from=d.isoformat(), date_to=d.isoformat())
    else:
        result = _parse_date_range(text)
        if not result:
            await message.answer(
                "Неверный формат. Введите диапазон в формате ДД.ММ.ГГГГ - ДД.ММ.ГГГГ:"
            )
            return
        d1, d2 = result
        if d2 < date.today():
            await message.answer("Диапазон уже прошёл. Введите актуальные даты:")
            return
        await state.update_data(date_from=d1.isoformat(), date_to=d2.isoformat())

    await state.set_state(None)
    await message.answer("Количество пересадок:", reply_markup=stops_select())


# --- Выбор пересадок → сводка + ввод цены ---

@router.callback_query(F.data.startswith("stops:"))
async def cb_stops_select(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    max_stops = int(callback.data.split(":")[1])
    await callback.answer()
    await state.update_data(max_stops=max_stops)

    data = await state.get_data()
    origin_iata = data.get("origin_iata")
    dest_type = data.get("pending_dest_type")
    dest_code = data.get("pending_dest_code")
    date_from = data.get("date_from")  # ISO строка или None
    date_to = data.get("date_to")      # ISO строка или None

    # Показываем "загрузка" пока получаем цены
    await callback.message.edit_text("⏳ Загружаем данные о ценах...")

    ref_price = await _get_reference_price(
        origin_iata, dest_type, dest_code, session, date_from, date_to
    )
    price_line = f"\n\n💰 Сейчас минимальная цена: ~{ref_price:,} ₽".replace(",", " ") if ref_price else ""

    text = (
        f"Сколько максимум вы готовы потратить на билет? (₽):\n"
        f"(например: 30000)"
        f"{price_line}"
    )
    await state.set_state(SubscribeStates.waiting_for_target_price)
    await callback.message.edit_text(text)


@router.message(SubscribeStates.waiting_for_target_price, ~F.text.startswith("/"))
async def process_target_price(
    message: Message, state: FSMContext, session: AsyncSession
):
    text = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        price = int(text)
    except ValueError:
        await message.answer("Введите целое число. Например: 30000")
        return

    if price <= 0:
        await message.answer("Цена должна быть больше нуля:")
        return

    await state.update_data(target_price=price)
    await _finalize_subscription(message, state, session)


# --- Создание подписки ---

async def _finalize_subscription(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Создать подписку из данных FSM."""
    data = await state.get_data()
    await state.clear()

    origin_iata = data.get("origin_iata")
    dest_type = data.get("pending_dest_type")
    dest_code = data.get("pending_dest_code")
    date_from = date.fromisoformat(data["date_from"]) if data.get("date_from") else None
    date_to = date.fromisoformat(data["date_to"]) if data.get("date_to") else None
    max_stops = data.get("max_stops")
    target_price = data.get("target_price")

    if not all([origin_iata, dest_type, dest_code, target_price]):
        logger.warning("user_id=%d: сессия истекла при финализации подписки", event.from_user.id)
        await _reply(event, "Сессия истекла. Начните заново с /subscribe")
        return

    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    tg_id = event.from_user.id
    user = await user_repo.get_by_telegram_id(tg_id)
    if not user:
        return

    editing_sub_id = data.get("editing_sub_id")

    if editing_sub_id:
        # Режим редактирования — обновляем существующую подписку
        updated = await sub_repo.update(
            editing_sub_id, user.id, origin_iata, dest_type, dest_code,
            date_from, date_to, max_stops, target_price,
        )
        if updated:
            logger.info(
                "user_id=%d: sub_id=%d обновлена: %s→%s:%s dates=%s/%s stops=%s price=%s",
                tg_id, editing_sub_id, origin_iata, dest_type, dest_code,
                date_from, date_to, max_stops, target_price,
            )
        else:
            logger.warning("user_id=%d: не удалось обновить sub_id=%d", tg_id, editing_sub_id)
        action_label = "✅ Подписка обновлена!" if updated else "⚠️ Не удалось обновить подписку."
    else:
        # Режим создания — проверяем лимит и создаём
        count = await sub_repo.count_active(user.id)
        if count >= 10:
            logger.warning("user_id=%d: достигнут лимит подписок (10)", tg_id)
            await _reply(
                event,
                "У вас уже 10 подписок — это максимум. "
                "Удалите одну из существующих, чтобы добавить новую.",
            )
            return

        try:
            await sub_repo.create(
                user.id, origin_iata, dest_type, dest_code,
                date_from, date_to, max_stops, target_price,
            )
            logger.info(
                "user_id=%d: подписка создана: %s→%s:%s dates=%s/%s stops=%s price=%s",
                tg_id, origin_iata, dest_type, dest_code,
                date_from, date_to, max_stops, target_price,
            )
        except IntegrityError:
            await session.rollback()
            logger.warning("user_id=%d: дубль подписки %s→%s:%s", tg_id, origin_iata, dest_type, dest_code)
            await _reply(event, "Такая подписка у вас уже есть.")
            return
        action_label = "✅ Подписка добавлена!"

    dest_label = await _dest_label(session, dest_type, dest_code)
    origin_name = await _city_name(session, origin_iata)
    date_line = _date_label(date_from, date_to).strip(" ·") or "любые даты"
    stops_line = STOPS_LABELS.get(max_stops, "") if max_stops is not None else "любые"
    price_str = f"{target_price:,} ₽".replace(",", " ")
    await _reply(
        event,
        f"{action_label}\n\n"
        f"✈️ {origin_name} → {dest_label}\n"
        f"📅 {date_line}\n"
        f"🔄 {stops_line}\n"
        f"💰 Уведомлять при цене ниже: {price_str}",
    )


async def _reply(event: Message | CallbackQuery, text: str) -> None:
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text)
    else:
        await event.answer(text)


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

    user = await user_repo.get_by_telegram_id(event.from_user.id)
    if not user:
        await _reply(event, "Сначала выполните /start")
        return

    subs = await sub_repo.get_user_subscriptions(user.id)
    if not subs:
        await _reply(event, "У вас пока нет подписок. Используйте /subscribe для добавления.")
        return

    dest_labels = {}
    for sub in subs:
        dest_label = await _dest_label(session, sub.dest_type, sub.dest_code)
        origin_name = await _city_name(session, sub.origin_iata)
        date_str = _date_label(sub.date_from, sub.date_to)
        price_str = (
            f" · ≤{sub.target_price:,} ₽".replace(",", " ")
            if sub.target_price else ""
        )
        dest_labels[sub.id] = f"{origin_name} → {dest_label}{date_str}{price_str}"

    text = f"Твои подписки ({len(subs)}/10):"
    kb = subscription_list(subs, dest_labels)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


# --- Редактирование подписки ---

@router.callback_query(F.data.startswith("edit_sub:"))
async def cb_edit_subscription(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    sub_id = int(callback.data.split(":")[1])
    await callback.answer()
    await state.update_data(editing_sub_id=sub_id)
    await callback.message.edit_text("Редактирование подписки:")
    await callback.message.answer(
        "Введите полное название города вылета на русском:",
        reply_markup=_origin_reply_kb(),
    )
    await state.set_state(SubscribeStates.waiting_for_origin_city)


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
        logger.info("user_id=%d: sub_id=%d удалена", callback.from_user.id, sub_id)
    else:
        logger.warning("user_id=%d: попытка удалить несуществующую sub_id=%d", callback.from_user.id, sub_id)
    await callback.answer("Подписка удалена" if success else "Подписка не найдена")
    await _show_subscriptions(callback, session)


# --- Хелперы ---

async def _city_name(session: AsyncSession, iata: str) -> str:
    stmt = select(City.name_ru).where(City.iata == iata)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() or iata


async def _dest_label(session: AsyncSession, dest_type: str, dest_code: str) -> str:
    if dest_type == "region":
        return dest_code
    if dest_type == "country":
        stmt = select(Country.name_ru).where(Country.code == dest_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() or dest_code
    if dest_type == "city":
        stmt = select(City.name_ru).where(City.iata == dest_code)
        result = await session.execute(stmt)
        name = result.scalar_one_or_none()
        return f"{name or dest_code}"
    return dest_code


async def _get_reference_price(
    origin_iata: str,
    dest_type: str,
    dest_code: str,
    session: AsyncSession,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int | None:
    """Получить минимальную цену для направления с учётом дат."""
    # Для конкретного города — прямой запрос по маршруту с фильтром дат
    if dest_type == "city":
        try:
            return await get_global_min_price(
                origin_iata, dest_code, date_from, date_to
            )
        except Exception:
            return None

    try:
        tickets = await get_cheap_tickets(origin_iata)
    except Exception:
        return None
    if not tickets:
        return None

    # Фильтрация по датам для страны/региона.
    # get_cheap_tickets возвращает по одному (глобально дешёвому) билету на направление —
    # его дата может не попасть в нужный диапазон. Если после фильтра пусто,
    # используем нефильтрованные данные как приблизительный ориентир.
    if date_from or date_to:
        filtered = [
            t for t in tickets
            if (not date_from or (t.get("departure_at") or "")[:10] >= date_from)
            and (not date_to or (t.get("departure_at") or "")[:10] <= date_to)
        ]
        if filtered:
            tickets = filtered

    if dest_type == "country":
        stmt = select(City.iata).where(City.country_code == dest_code)
        result = await session.execute(stmt)
        city_iatas = {row[0] for row in result.all()}
        matching = [t for t in tickets if t["destination_iata"] in city_iatas]
    elif dest_type == "region":
        country_codes = _REGIONS.get(dest_code, [])
        stmt = select(City.iata).where(City.country_code.in_(country_codes))
        result = await session.execute(stmt)
        city_iatas = {row[0] for row in result.all()}
        matching = [t for t in tickets if t["destination_iata"] in city_iatas]
    else:
        return None

    prices = [t["price"] for t in matching if t["price"] > 0]
    return min(prices) if prices else None


def _date_label(date_from: date | None, date_to: date | None) -> str:
    if not date_from:
        return ""
    if date_from == date_to:
        return f" · {date_from.day} {MONTHS_GEN[date_from.month]} {date_from.year}"
    last_day = monthrange(date_from.year, date_from.month)[1]
    if (
        date_from.day == 1
        and date_to.month == date_from.month
        and date_to.year == date_from.year
        and date_to.day == last_day
    ):
        return f" · {MONTHS_NOM[date_from.month]} {date_from.year}"
    return f" · {date_from.strftime('%d.%m')}–{date_to.strftime('%d.%m.%Y')}"


def _parse_single_date(s: str) -> date | None:
    for fmt in ["%d.%m.%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_date_range(text: str) -> tuple[date, date] | None:
    for sep in [" - ", " – ", " — ", "-", "–", "—"]:
        if sep in text:
            parts = text.split(sep, 1)
            d1 = _parse_single_date(parts[0])
            d2 = _parse_single_date(parts[1])
            if d1 and d2:
                return (min(d1, d2), max(d1, d2))
    return None
