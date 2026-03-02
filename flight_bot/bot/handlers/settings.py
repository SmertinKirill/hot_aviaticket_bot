"""Настройки: /settings, /setorigin."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import city_select, main_menu, threshold_select
from bot.states import OnboardingStates
from core.db.models import City
from core.db.repositories.user_repo import UserRepository

router = Router()
logger = logging.getLogger(__name__)


# --- /setorigin ---

@router.message(Command("setorigin"))
async def cmd_setorigin(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполните /start")
        return

    await message.answer("Введите новый город вылета:")
    await state.set_state(OnboardingStates.waiting_for_city)
    await state.update_data(setorigin=True)


@router.callback_query(F.data.startswith("setorigin_city:"))
async def cb_setorigin_city(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    iata = callback.data.split(":")[1]
    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    await user_repo.update_origin(user.id, iata)
    await state.clear()

    stmt = select(City.name_ru).where(City.iata == iata)
    result = await session.execute(stmt)
    city_name = result.scalar_one_or_none() or iata

    await callback.message.edit_text(
        f"Город вылета обновлён: {city_name} ({iata})"
    )


# --- /settings ---

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

    # Название города
    origin_label = "не задан"
    if user.origin_iata:
        stmt = select(City.name_ru).where(City.iata == user.origin_iata)
        result = await session.execute(stmt)
        origin_name = result.scalar_one_or_none()
        origin_label = f"{origin_name or user.origin_iata} ({user.origin_iata})"

    text = (
        f"⚙️ Настройки\n\n"
        f"🏠 Город вылета: {origin_label}\n"
        f"   (изменить: /setorigin)\n\n"
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
