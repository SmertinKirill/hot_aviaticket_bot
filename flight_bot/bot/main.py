"""Точка входа Telegram-бота (long polling)."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, MenuButtonCommands

from bot.handlers import admin, settings, start, subscriptions
from bot.middleware import DbSessionMiddleware, LoggingMiddleware, RateLimitMiddleware
from bootstrap.load_references import load_if_empty
from core.config import TELEGRAM_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> None:
    if isinstance(event.exception, TelegramBadRequest) and "message is not modified" in str(event.exception):
        return
    logger.exception("Необработанная ошибка: %s", event.exception)


async def main() -> None:
    logger.info("Bot: запуск")

    # Загрузить справочники если пусто
    await load_if_empty()

    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.errors.register(on_error)

    # Middleware
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    # Роутеры
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(subscriptions.router)
    dp.include_router(settings.router)

    # Регистрируем команды (показываются в меню "/" и кнопке слева)
    await bot.set_my_commands([
        BotCommand(command="subscribe", description="Добавить подписку"),
        BotCommand(command="mysubscriptions", description="Мои подписки"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="start", description="Главное меню"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    logger.info("Bot: начинаем polling")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Bot: остановлен")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
