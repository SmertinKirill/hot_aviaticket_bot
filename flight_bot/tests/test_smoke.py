"""Smoke-тест: отправляет реальное тестовое уведомление пользователю с id=1 в БД.

Запуск:
    pytest -m smoke

Требует: .env с TELEGRAM_TOKEN и DATABASE_URL, запущенную БД, пользователя с id=1.
"""

import pytest
from aiogram import Bot
from sqlalchemy import select

from core.config import TELEGRAM_TOKEN
from core.db.base import async_session
from core.db.models import User
from scheduler.tasks import _send_notification


@pytest.mark.smoke
async def test_send_test_notification_to_first_user():
    """Отправляет тестовое уведомление первому зарегистрированному пользователю (id=1)."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == 1))
        user = result.scalar_one_or_none()

    assert user is not None, "Пользователь с id=1 не найден в БД — запустите бота и зарегистрируйтесь"

    deal = {
        "current_price": 7_500,
        "target_price": 10_000,
        "prev_price": None,
        "origin_iata": "MOW",
        "dest_iata": "BKK",
        "route_key": "MOW:BKK:2026-04-15",
        "ticket_link": "https://aviasales.ru",
        "stops": 0,
        "layover": None,
    }

    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        async with async_session() as session:
            sent = await _send_notification(bot, user.telegram_id, deal, session)
        assert sent is True, "Уведомление не отправлено — проверьте токен и telegram_id"
    finally:
        await bot.session.close()
