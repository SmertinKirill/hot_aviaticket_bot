"""Команды для администраторов."""

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import AdminReplyStates, BroadcastStates, SupportStates
from core.config import ADMIN_IDS
from core.db.models import User
from core.db.repositories.support_ticket_repo import SupportTicketRepository
from scheduler.tasks import build_stats_text

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


# ── Stats ────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession):
    if not _is_admin(message.from_user.id):
        return
    text = await build_stats_text(session)
    await message.answer(text)


# ── Broadcast ────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastStates.waiting_for_text)
    await message.answer(
        "✍️ Введите текст для рассылки всем активным пользователям.\n\n"
        "/cancel — отмена."
    )


@router.message(Command("cancel"), BroadcastStates.waiting_for_text)
async def cmd_cancel_broadcast(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Рассылка отменена.")


@router.message(BroadcastStates.waiting_for_text, F.text)
async def process_broadcast_text(message: Message, state: FSMContext, session: AsyncSession):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    await state.clear()
    text = message.text

    result = await session.execute(
        select(User.telegram_id).where(User.is_active == True)  # noqa: E712
    )
    recipients = [row[0] for row in result.all()]

    sent = 0
    errors = 0
    for telegram_id in recipients:
        try:
            await message.bot.send_message(telegram_id, text)
            sent += 1
        except TelegramRetryAfter as e:
            logger.warning("Broadcast: rate limit, ждём %d сек", e.retry_after)
            await asyncio.sleep(e.retry_after)
            try:
                await message.bot.send_message(telegram_id, text)
                sent += 1
            except Exception as e2:
                logger.warning("Broadcast: ошибка после retry user=%d: %s", telegram_id, e2)
                errors += 1
        except Exception as e:
            logger.warning("Broadcast: ошибка для user=%d: %s", telegram_id, e)
            errors += 1
        await asyncio.sleep(0.05)

    await message.answer(f"✅ Отправлено: {sent}\n❌ Ошибок: {errors}")


# ── Support (user side) ───────────────────────────────────────────────────────

@router.callback_query(F.data == "support")
async def cb_support(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SupportStates.waiting_for_message)
    await callback.message.answer(
        "✍️ Опишите ваш вопрос или проблему — мы ответим вам в чате.\n\n"
        "/cancel — отмена."
    )


@router.message(Command("cancel"), SupportStates.waiting_for_message)
async def cancel_support(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.")


@router.message(SupportStates.waiting_for_message, F.text)
async def process_support_message(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    user = message.from_user

    user_name = user.full_name
    if user.username:
        user_name += f" (@{user.username})"

    ticket_repo = SupportTicketRepository(session)
    ticket = await ticket_repo.create(
        user_telegram_id=user.id,
        user_name=user_name,
        message=message.text,
    )

    support_text = (
        f"📨 Обращение в поддержку  #{ticket.id}\n\n"
        f"👤 {user_name}\n"
        f"🆔 {user.id}\n\n"
        f"💬 {message.text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="↩️ Ответить",
            callback_data=f"reply_to:{user.id}:{ticket.id}",
        )
    ]])

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, support_text, reply_markup=kb)
        except Exception as e:
            logger.warning("Support: ошибка отправки admin=%d: %s", admin_id, e)

    await message.answer("✅ Сообщение отправлено в поддержку. Ожидайте ответа.")


# ── Support (admin reply side) ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reply_to:"))
async def cb_reply_to(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_id = int(parts[1])
    ticket_id = int(parts[2])

    await state.set_state(AdminReplyStates.waiting_for_reply)
    await state.update_data(reply_to=target_id, ticket_id=ticket_id)
    await callback.answer()
    await callback.message.answer(
        f"✍️ Введите ответ на обращение #{ticket_id} (пользователь {target_id}).\n\n"
        "/cancel — отмена."
    )


@router.message(Command("cancel"), AdminReplyStates.waiting_for_reply)
async def cancel_admin_reply(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Ответ отменён.")


@router.message(AdminReplyStates.waiting_for_reply, F.text)
async def process_admin_reply(message: Message, state: FSMContext, session: AsyncSession):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    target_id: int = data["reply_to"]
    ticket_id: int = data["ticket_id"]
    await state.clear()

    ticket_repo = SupportTicketRepository(session)
    await ticket_repo.set_reply(
        ticket_id=ticket_id,
        reply=message.text,
        admin_telegram_id=message.from_user.id,
    )

    reply_text = f"💬 Ответ от поддержки (обращение #{ticket_id}):\n\n{message.text}"
    try:
        await message.bot.send_message(target_id, reply_text)
        await message.answer(f"✅ Ответ на обращение #{ticket_id} отправлен пользователю {target_id}.")
    except Exception as e:
        logger.warning("Admin reply: ошибка отправки user=%d: %s", target_id, e)
        await message.answer(f"❌ Не удалось отправить: {e}")
