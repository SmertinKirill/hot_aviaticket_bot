"""Задачи мониторинга цен и отправки уведомлений."""

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import analyzer
from core.api import cache
from core.api.travelpayouts import get_cheap_tickets
from core.db.base import async_session
from core.db.models import Airport, City, Country, Subscription
from core.db.repositories.notification_repo import NotificationRepository
from core.db.repositories.price_history_repo import PriceHistoryRepository
from core.db.repositories.subscription_repo import SubscriptionRepository

logger = logging.getLogger(__name__)

REGIONS = {
    "ЮВА": ["TH", "VN", "ID", "MY", "SG", "PH", "KH", "MM", "LA"],
    "ОАЭ и Ближний Восток": [
        "AE", "QA", "JO", "LB", "BH", "KW", "OM", "SA",
    ],
    "Европа": [
        "DE", "FR", "IT", "ES", "CZ", "AT", "NL", "PL", "GR", "HR",
        "PT", "HU", "RO", "BG", "RS", "ME", "AL", "MK", "TR", "GE", "AM",
    ],
}

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


async def resolve_destinations(
    subscription: Subscription, session: AsyncSession
) -> list[str]:
    """Разрешить подписку в список IATA-кодов городов назначения."""
    if subscription.dest_type == "city":
        # Для города возвращаем IATA самого города (не аэропортов)
        return [subscription.dest_code]

    if subscription.dest_type == "country":
        stmt = select(City.iata).where(
            City.country_code == subscription.dest_code
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]

    if subscription.dest_type == "region":
        country_codes = REGIONS.get(subscription.dest_code, [])
        if not country_codes:
            return []
        stmt = select(City.iata).where(
            City.country_code.in_(country_codes)
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]

    return []


def _format_date_ru(date_str: str) -> str:
    """Форматировать дату YYYY-MM-DD на русском."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year}"
    except (ValueError, KeyError):
        return date_str


async def _get_city_name(iata: str, session: AsyncSession) -> str:
    """Получить русское название города по IATA."""
    stmt = select(City.name_ru).where(City.iata == iata)
    result = await session.execute(stmt)
    name = result.scalar_one_or_none()
    return name or iata


async def _send_notification(
    bot: Bot, telegram_id: int, deal: dict, session: AsyncSession
) -> None:
    """Отправить уведомление о горящем билете."""
    origin_name = await _get_city_name(deal["origin_iata"], session)
    dest_name = await _get_city_name(deal["dest_iata"], session)

    # Извлечь дату из route_key: MOW:BKK:2025-03-15
    parts = deal["route_key"].split(":")
    date_str = parts[2] if len(parts) >= 3 else ""
    date_formatted = _format_date_ru(date_str)

    text = (
        f"🔥 Горящий билет!\n\n"
        f"{origin_name} → {dest_name} ({deal['dest_iata']})\n"
        f"📅 Вылет: {date_formatted}\n"
        f"💰 {deal['current_price']:,} ₽  "
        f"(обычно ~{deal['base_price']:,} ₽, "
        f"дешевле на {deal['discount_pct']}%)\n\n"
        f"⚡ Цена может измениться — бронируйте быстро"
    ).replace(",", " ")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👉 Купить билет", url=deal["ticket_link"]
                )
            ]
        ]
    )

    try:
        await bot.send_message(telegram_id, text, reply_markup=keyboard)
    except Exception as e:
        logger.error(
            "Ошибка отправки уведомления user=%d: %s", telegram_id, e
        )


async def monitor_cycle(bot: Bot) -> None:
    """Основной цикл мониторинга цен."""
    try:
        logger.info("Цикл мониторинга: начало")

        async with async_session() as session:
            sub_repo = SubscriptionRepository(session)
            price_repo = PriceHistoryRepository(session)
            notif_repo = NotificationRepository(session)

            all_subs = await sub_repo.get_all_active()

            # Группируем по origin_iata
            origin_subs: dict[str, list[Subscription]] = {}
            for sub in all_subs:
                origin_subs.setdefault(sub.origin_iata, []).append(sub)

            logger.info(
                "Города вылета: %d, подписок: %d",
                len(origin_subs),
                len(all_subs),
            )

            total_routes = 0
            total_deals = 0

            for origin, subs in origin_subs.items():
                # Получить тикеты из кэша или API
                tickets = await cache.get_prices(origin)
                if tickets is None:
                    tickets = await get_cheap_tickets(origin)
                    if tickets:
                        await cache.set_prices(origin, tickets)

                # Множество доступных направлений
                available_dest_iata = {t["destination_iata"] for t in tickets}

                # Записать в price_history
                for ticket in tickets:
                    dest = ticket["destination_iata"]
                    departure = ticket["departure_at"]
                    if not dest or not departure:
                        continue
                    route_key = f"{origin}:{dest}:{departure}"
                    await price_repo.add(
                        route_key=route_key,
                        price=ticket["price"],
                        ticket_link=ticket["ticket_link"],
                    )

                # Проверить подписки
                for sub in subs:
                    destinations = await resolve_destinations(sub, session)
                    # Фильтрация по реальным направлениям
                    destinations = [
                        d for d in destinations if d in available_dest_iata
                    ]

                    for dest in destinations:
                        total_routes += 1
                        deal = await analyzer.check(sub, origin, dest, session)
                        if deal is not None:
                            total_deals += 1
                            # Записать уведомление
                            await notif_repo.create(
                                subscription_id=deal["subscription_id"],
                                route_key=deal["route_key"],
                                price=deal["current_price"],
                                avg_price=deal["base_price"],
                                discount_pct=deal["discount_pct"],
                            )
                            # Отправить
                            await _send_notification(
                                bot, sub.user.telegram_id, deal, session
                            )
                            logger.info(
                                "Уведомление: user_id=%d, sub_id=%d, "
                                "route=%s, price=%d, discount=%d%%",
                                sub.user.id,
                                sub.id,
                                deal["route_key"],
                                deal["current_price"],
                                deal["discount_pct"],
                            )

            logger.info(
                "Цикл мониторинга: завершён. "
                "Проверено маршрутов: %d, найдено горящих: %d",
                total_routes,
                total_deals,
            )

    except Exception as e:
        logger.error("Ошибка цикла мониторинга: %s", e)


async def clean_old_prices() -> None:
    """Удаление старых записей price_history (retention policy)."""
    try:
        async with async_session() as session:
            price_repo = PriceHistoryRepository(session)
            deleted = await price_repo.delete_older_than(weeks=12)
            logger.info("Retention: удалено %d записей старше 12 недель", deleted)
    except Exception as e:
        logger.error("Ошибка retention job: %s", e)
