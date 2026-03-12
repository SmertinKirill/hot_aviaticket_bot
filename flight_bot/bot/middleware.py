"""Middleware для инъекции AsyncSession в хендлеры."""

import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.api.cache import get_redis
from core.config import ADMIN_IDS
from core.db.base import async_session

logger = logging.getLogger(__name__)

_RATE_LIMIT = 20       # запросов
_RATE_WINDOW = 10      # секунд


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            name = f"@{user.username}" if user.username else f"id={user.id}"
            if isinstance(event, Message) and event.text:
                logger.info("User %s: %s", name, event.text[:80])
            elif isinstance(event, CallbackQuery):
                logger.info("User %s: callback=%s", name, event.data)
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id in ADMIN_IDS:
            return await handler(event, data)

        window = int(time.time()) // _RATE_WINDOW
        key = f"rl:{user.id}:{window}"

        r = await get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, _RATE_WINDOW * 2)

        if count > _RATE_LIMIT:
            if count == _RATE_LIMIT + 1:
                if isinstance(event, Message):
                    await event.answer("⏳ Слишком много запросов, подождите немного.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⏳ Слишком много запросов, подождите немного.", show_alert=False)
            return None

        return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            data["session"] = session
            return await handler(event, data)
