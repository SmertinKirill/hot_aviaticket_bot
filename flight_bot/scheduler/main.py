"""Точка входа для scheduler-контейнера."""

import asyncio
import logging
import signal

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import TELEGRAM_TOKEN
from scheduler.tasks import clean_old_prices, monitor_cycle, send_weekly_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Scheduler: запуск")

    bot = Bot(token=TELEGRAM_TOKEN)
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        monitor_cycle, "interval", minutes=15, args=[bot], id="monitor",
        max_instances=1,
    )
    scheduler.add_job(
        clean_old_prices, "interval", days=1, id="retention"
    )
    scheduler.add_job(
        send_weekly_stats, "cron",
        day_of_week="thu", hour=12, minute=0,
        args=[bot], id="weekly_stats",
        timezone="Europe/Moscow",
    )

    scheduler.start()
    logger.info("Scheduler: задачи запланированы")

    # Запустить первый цикл сразу
    await monitor_cycle(bot)

    stop_event = asyncio.Event()

    def _shutdown(sig, frame):
        logger.info("Scheduler: получен сигнал %s, останавливаемся", sig)
        scheduler.shutdown(wait=False)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    await stop_event.wait()
    await bot.session.close()
    logger.info("Scheduler: остановлен")


if __name__ == "__main__":
    asyncio.run(main())
