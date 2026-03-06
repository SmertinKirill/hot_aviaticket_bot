"""Задачи мониторинга цен и отправки уведомлений."""

import asyncio
import logging
from datetime import date, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import analyzer
from core.api.travelpayouts import get_route_tickets
from core.db.base import async_session
from core.db.models import Airport, City, Country, Subscription, User
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
    "Море": [
        "TR", "CY", "EG", "TN", "MA",  # Средиземноморье и Африка
        "GR", "HR", "ME", "BG",         # Европейское побережье
        "TH", "ID", "MV", "LK",         # Азия и острова
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


def _is_quiet_time(quiet_from: int, quiet_to: int) -> bool:
    """Проверить, находимся ли в тихом периоде (московское время, UTC+3)."""
    hour = (datetime.utcnow().hour + 3) % 24
    if quiet_from > quiet_to:  # диапазон пересекает полночь: 22–08
        return hour >= quiet_from or hour < quiet_to
    return quiet_from <= hour < quiet_to


async def _send_notification(
    bot: Bot, telegram_id: int, deal: dict, session: AsyncSession
) -> bool:
    """Отправить уведомление о горящем билете. Возвращает True при успехе."""
    origin_name = await _get_city_name(deal["origin_iata"], session)
    dest_name = await _get_city_name(deal["dest_iata"], session)

    # Извлечь дату из route_key: MOW:BKK:2025-03-15
    parts = deal["route_key"].split(":")
    date_str = parts[2] if len(parts) >= 3 else ""
    date_formatted = _format_date_ru(date_str)

    stops = deal.get("stops")
    if stops == 0:
        stops_line = "✈️ Прямой рейс"
    elif stops == 1:
        stops_line = "🔄 1 пересадка"
    elif stops is not None:
        stops_line = f"🔄 {stops} пересадки"
    else:
        stops_line = ""

    text = (
        f"🔥 Горящий билет!\n\n"
        f"{origin_name} → {dest_name} ({deal['dest_iata']})\n"
        f"📅 Вылет: {date_formatted}\n"
        + (f"{stops_line}\n" if stops_line else "")
        + f"💰 {deal['current_price']:,} ₽  "
        f"(ваш порог: {deal['target_price']:,} ₽)\n\n"
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

    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    silent = (
        user is not None
        and user.quiet_from is not None
        and _is_quiet_time(user.quiet_from, user.quiet_to)
    )

    try:
        await bot.send_message(
            telegram_id, text, reply_markup=keyboard, disable_notification=silent
        )
        await asyncio.sleep(0.05)  # не более 20 сообщений/сек (лимит TG: 30/сек)
        return True
    except TelegramRetryAfter as e:
        logger.warning("Telegram rate limit, ждём %d сек", e.retry_after)
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(
                telegram_id, text, reply_markup=keyboard, disable_notification=silent
            )
            return True
        except Exception as e2:
            logger.error("Ошибка отправки после retry user=%d: %s", telegram_id, e2)
            return False
    except Exception as e:
        logger.error("Ошибка отправки уведомления user=%d: %s", telegram_id, e)
        return False


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
                # City-подписки: запрашиваем конкретный маршрут с фильтром дат.
                # Дедупликация: один запрос на уникальный (dest, date_from, date_to).
                extra_tickets: list[dict] = []
                seen_routes: dict[tuple, list[dict]] = {}
                for sub in subs:
                    if sub.dest_type == "city" and sub.date_from is not None:
                        key = (sub.dest_code, sub.date_from, sub.date_to)
                        if key not in seen_routes:
                            route_t = await get_route_tickets(
                                origin,
                                sub.dest_code,
                                sub.date_from.isoformat(),
                                sub.date_to.isoformat(),
                            )
                            await asyncio.sleep(0.5)
                            seen_routes[key] = route_t
                        extra_tickets.extend(seen_routes[key])

                # Для country/region подписок: дёргаем /v3/prices_for_dates
                # с кодом страны. date_from нормализуем до начала месяца —
                # все подписки в одном месяце дают один запрос/кеш-ключ.
                # Точная фильтрация дат — в памяти через _ticket_matches.
                # Ключ дедупликации: (country, YYYY-MM).
                seen_country_months: dict[tuple, list[dict]] = {}
                for sub in subs:
                    if sub.dest_type == "country":
                        country_codes = [sub.dest_code]
                    elif sub.dest_type == "region":
                        country_codes = REGIONS.get(sub.dest_code, [])
                    else:
                        continue

                    month_key = sub.date_from.strftime("%Y-%m") if sub.date_from else ""

                    for cc in country_codes:
                        key = (cc, month_key)
                        if key not in seen_country_months:
                            cc_tickets = await get_route_tickets(origin, cc, departure_month=month_key)
                            await asyncio.sleep(0.5)
                            seen_country_months[key] = cc_tickets
                        extra_tickets.extend(seen_country_months[key])

                all_tickets = extra_tickets

                # Записать в price_history + собрать lookup stops по route_key
                stops_lookup: dict[str, int | None] = {}
                for ticket in all_tickets:
                    dest = ticket["destination_iata"]
                    departure = ticket["departure_at"]
                    if not dest or not departure:
                        continue
                    route_key = f"{origin}:{dest}:{departure}"
                    stops_lookup[route_key] = ticket.get("stops")
                    await price_repo.add(
                        route_key=route_key,
                        price=ticket["price"],
                        ticket_link=ticket["ticket_link"],
                    )

                # Проверить подписки
                for sub in subs:
                    destinations = await resolve_destinations(sub, session)
                    # Фильтрация тикетов по дате и пересадкам подписки
                    def _ticket_matches(t: dict) -> bool:
                        if sub.date_from is not None:
                            d = _parse_ticket_date(t["departure_at"])
                            if not (sub.date_from <= d <= sub.date_to):
                                return False
                        if sub.max_stops is not None:
                            stops = t.get("stops")
                            if stops is not None and stops > sub.max_stops:
                                return False
                        return True

                    sub_available = {
                        t["destination_iata"] for t in all_tickets
                        if _ticket_matches(t)
                    }
                    destinations = [
                        d for d in destinations if d in sub_available
                    ]

                    for dest in destinations:
                        total_routes += 1
                        deal = await analyzer.check(sub, origin, dest, session)
                        if deal is not None:
                            deal["stops"] = stops_lookup.get(deal["route_key"])
                            total_deals += 1
                            savings_pct = round(
                                (deal["target_price"] - deal["current_price"])
                                / deal["target_price"] * 100
                            ) if deal["target_price"] > 0 else 0
                            # Отправить — записываем в БД только при успехе
                            sent = await _send_notification(
                                bot, sub.user.telegram_id, deal, session
                            )
                            if sent:
                                await notif_repo.create(
                                    subscription_id=deal["subscription_id"],
                                    route_key=deal["route_key"],
                                    price=deal["current_price"],
                                    avg_price=deal["target_price"],
                                    discount_pct=savings_pct,
                                )
                            logger.info(
                                "Уведомление: user_id=%d, sub_id=%d, "
                                "route=%s, price=%d, savings=%d%%",
                                sub.user.id,
                                sub.id,
                                deal["route_key"],
                                deal["current_price"],
                                savings_pct,
                            )

            logger.info(
                "Цикл мониторинга: завершён. "
                "Проверено маршрутов: %d, найдено горящих: %d",
                total_routes,
                total_deals,
            )

    except Exception as e:
        logger.error("Ошибка цикла мониторинга: %s", e)


def _parse_ticket_date(departure_at: str) -> date:
    """Парсим YYYY-MM-DD из поля departure_at тикета."""
    try:
        return datetime.strptime(departure_at[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return date.min


async def clean_old_prices() -> None:
    """Удаление старых записей price_history (retention policy)."""
    try:
        async with async_session() as session:
            price_repo = PriceHistoryRepository(session)
            deleted = await price_repo.delete_older_than(weeks=12)
            logger.info("Retention: удалено %d записей старше 12 недель", deleted)
    except Exception as e:
        logger.error("Ошибка retention job: %s", e)
