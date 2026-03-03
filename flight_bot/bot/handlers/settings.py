"""Настройки: /settings."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import quiet_hours_menu
from core.db.repositories.subscription_repo import SubscriptionRepository
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession):
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
        quiet_label = f"🔇 {user.quiet_from:02d}:00 – {user.quiet_to:02d}:00 (МСК)"
    else:
        quiet_label = "🔔 выключен"

    text = (
        f"⚙️ Настройки\n\n"
        f"📋 Активных подписок: {count}/10\n"
        f"🌙 Тихий режим: {quiet_label}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌙 Тихий режим", callback_data="quiet_menu")],
    ])

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "quiet_menu")
async def cb_quiet_menu(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    await callback.message.edit_text(
        "🌙 Тихий режим\n\n"
        "В выбранный период уведомления придут без звука (по московскому времени).",
        reply_markup=quiet_hours_menu(user.quiet_from if user else None),
    )


@router.callback_query(F.data.startswith("quiet:"))
async def cb_quiet_set(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    value = callback.data.split(":", 1)[1]
    if value == "off":
        await user_repo.update_quiet_hours(user.id, None, None)
        await callback.message.edit_text(
            "🔔 Тихий режим отключён. Уведомления будут приходить со звуком.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← Назад", callback_data="settings")
            ]]),
        )
    else:
        qf, qt = map(int, value.split(":"))
        await user_repo.update_quiet_hours(user.id, qf, qt)
        await callback.message.edit_text(
            f"🔇 Тихий режим: {qf:02d}:00 – {qt:02d}:00 (МСК)\n\n"
            "В это время уведомления придут без звука.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← Назад", callback_data="settings")
            ]]),
        )
