"""Настройки: /settings."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import threshold_select
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


async def _show_settings(
    event: Message | CallbackQuery, session: AsyncSession
):
    user_repo = UserRepository(session)
    tg_id = event.from_user.id
    user = await user_repo.get_by_telegram_id(tg_id)

    if not user:
        text = "Сначала выполните /start"
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
        else:
            await event.answer(text)
        return

    text = (
        f"⚙️ Настройки\n\n"
        f"📊 Текущий порог уведомлений: {user.threshold_pct}%\n"
        f"Уведомлять если цена ниже обычной на:"
    )
    kb = threshold_select(user.threshold_pct)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("threshold:"))
async def cb_threshold(callback: CallbackQuery, session: AsyncSession):
    value = int(callback.data.split(":")[1])
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    try:
        await user_repo.update_threshold(user.id, value)
        await callback.answer(f"Порог обновлён: {value}%")
        await _show_settings(callback, session)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
