"""Настройки: /settings."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _show_settings(
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

    count = await sub_repo.count_active(user.id)
    text = (
        f"⚙️ Настройки\n\n"
        f"📋 Активных подписок: {count}/10\n\n"
        f"Параметры уведомлений (цена, пересадки, даты) "
        f"задаются отдельно для каждой подписки."
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text)
    else:
        await event.answer(text)
