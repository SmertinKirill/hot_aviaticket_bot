"""Настройки: /settings."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import currency_select, timezone_select
from bot.states import QuietHoursStates
from core.config import ADMIN_IDS
from core.db.repositories.subscription_repo import SubscriptionRepository
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    tmp = await message.answer("…", reply_markup=ReplyKeyboardRemove())
    await tmp.delete()
    await _show_settings(message, session)


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    await _show_settings(callback, session)


async def _show_settings(event: Message | CallbackQuery, session: AsyncSession):
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)
    user = await user_repo.get_by_telegram_id(event.from_user.id)

    if not user:
        text = "Сначала выполните /start"
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
        else:
            await event.answer(text)
        return

    count = await sub_repo.count_active(user.id)

    if user.quiet_from is not None:
        tz = user.quiet_timezone or 3
        tz_label = f"UTC+{tz}" if tz >= 0 else f"UTC{tz}"
        quiet_label = f"🔇 {user.quiet_from:02d}:00 – {user.quiet_to:02d}:00 ({tz_label})"
    else:
        quiet_label = "🔔 выключен"

    currency = user.default_currency or "RUB"
    currency_label = {"RUB": "🇷🇺 Рубли (₽)", "USD": "🇺🇸 Доллары ($)", "EUR": "🇪🇺 Евро (€)"}.get(currency, currency)

    text = (
        f"⚙️ Настройки\n\n"
        f"📋 Активных подписок: {count}/10\n"
        f"💱 Валюта: {currency_label}\n"
        f"🌙 Тихий режим: {quiet_label}"
    )
    rows = [
        [InlineKeyboardButton(text="💱 Валюта", callback_data="currency_menu")],
        [InlineKeyboardButton(text="🌙 Тихий режим", callback_data="quiet_menu")],
    ]
    if ADMIN_IDS:
        rows.append([InlineKeyboardButton(text="💬 Поддержка", callback_data="support")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "currency_menu")
async def cb_currency_menu(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    current = user.default_currency if user else "RUB"
    await callback.message.edit_text(
        "💱 Валюта по умолчанию\n\n"
        "Новые подписки будут создаваться в этой валюте.\n"
        "Уже существующие подписки своей валюты не меняют.",
        reply_markup=currency_select(current=current),
    )


@router.callback_query(F.data.startswith("set_currency:"))
async def cb_set_currency(callback: CallbackQuery, session: AsyncSession):
    currency = callback.data.split(":")[1]
    await callback.answer()
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return
    await user_repo.update_default_currency(user.id, currency)
    label = {"RUB": "🇷🇺 Рубли (₽)", "USD": "🇺🇸 Доллары ($)", "EUR": "🇪🇺 Евро (€)"}.get(currency, currency)
    await callback.message.edit_text(
        f"💱 Валюта сохранена: {label}\n\n"
        "Новые подписки будут создаваться в этой валюте.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="← Назад", callback_data="settings")
        ]]),
    )


@router.callback_query(F.data == "quiet_menu")
async def cb_quiet_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()
    await state.clear()
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    current_tz = user.quiet_timezone if user else None
    await callback.message.edit_text(
        "🌙 Тихий режим\n\n"
        "Выберите ваш часовой пояс. Затем укажете диапазон часов, в которые уведомления будут приходить без звука.",
        reply_markup=timezone_select(current_tz),
    )


@router.callback_query(F.data == "quiet:off")
async def cb_quiet_off(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await callback.answer()
    await state.clear()
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return
    await user_repo.update_quiet_hours(user.id, None, None, None)
    await callback.message.edit_text(
        "🔔 Тихий режим отключён. Уведомления будут приходить со звуком.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="← Назад", callback_data="settings")
        ]]),
    )


@router.callback_query(F.data.startswith("quiet_tz:"))
async def cb_quiet_timezone(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tz = int(callback.data.split(":")[1])
    await state.set_state(QuietHoursStates.waiting_for_range)
    await state.update_data(quiet_tz=tz)
    tz_label = f"UTC+{tz}" if tz >= 0 else f"UTC{tz}"
    await callback.message.edit_text(
        f"🌙 Тихий режим — {tz_label}\n\n"
        "Введите диапазон в формате <b>начало-конец</b>, например: <b>22-9</b>\n\n"
        "Уведомления будут приходить без звука с 22:00 до 09:00.",
        parse_mode="HTML",
    )


@router.message(QuietHoursStates.waiting_for_range)
async def msg_quiet_range(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    parts = text.split("-")
    valid = (
        len(parts) == 2
        and parts[0].isdigit()
        and parts[1].isdigit()
        and 0 <= int(parts[0]) <= 23
        and 0 <= int(parts[1]) <= 23
    )
    if not valid:
        await message.answer("Неверный формат. Введите диапазон вида <b>22-9</b>.", parse_mode="HTML")
        return

    quiet_from, quiet_to = int(parts[0]), int(parts[1])
    data = await state.get_data()
    tz = data["quiet_tz"]
    await state.clear()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        return
    await user_repo.update_quiet_hours(user.id, quiet_from, quiet_to, tz)

    tz_label = f"UTC+{tz}" if tz >= 0 else f"UTC{tz}"
    await message.answer(
        f"🔇 Тихий режим сохранён: {quiet_from:02d}:00 – {quiet_to:02d}:00 ({tz_label})\n\n"
        "В это время уведомления будут приходить без звука.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="← Назад в настройки", callback_data="settings")
        ]]),
    )
