"""Задачи мониторинга цен и отправки уведомлений."""

import asyncio
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core import analyzer
from core.api.travelpayouts import get_partner_stats, get_route_tickets, shorten_link
from core.db.base import async_session
from core.db.models import Airport, City, Country, Notification, Subscription, User
from core.config import ADMIN_IDS
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


async def _get_country_name(city_iata: str, session: AsyncSession) -> str | None:
    """Получить русское название страны по IATA города."""
    stmt = (
        select(Country.name_ru)
        .join(City, City.country_code == Country.code)
        .where(City.iata == city_iata)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


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
    deal["ticket_link"] = await shorten_link(deal["ticket_link"])

    origin_name = await _get_city_name(deal["origin_iata"], session)
    dest_name = await _get_city_name(deal["dest_iata"], session)
    country_name = await _get_country_name(deal["dest_iata"], session)

    # Извлечь дату из route_key: MOW:BKK:2025-03-15
    parts = deal["route_key"].split(":")
    date_str = parts[2] if len(parts) >= 3 else ""
    date_formatted = _format_date_ru(date_str)

    stops = deal.get("stops")
    layover = deal.get("layover")
    if stops == 0:
        stops_line = "✈️ Прямой рейс"
    elif stops == 1:
        layover_str = f" ({layover // 60} ч {layover % 60} мин)" if layover else ""
        stops_line = f"🔄 1 пересадка{layover_str}"
    elif stops is not None:
        layover_str = f" ({layover // 60} ч {layover % 60} мин)" if layover else ""
        stops_line = f"🔄 {stops} пересадки{layover_str}"
    else:
        stops_line = ""

    prev_price = deal.get("prev_price")
    if prev_price is not None and prev_price > deal["current_price"]:
        drop = prev_price - deal["current_price"]
        drop_line = f"📉 −{drop:,} ₽ от прошлого уведомления\n"
    else:
        drop = deal["target_price"] - deal["current_price"]
        drop_line = f"📉 −{drop:,} ₽ от установленной вами цены\n"

    text = (
        f"🔥 Горящий билет!\n\n"
        f"{origin_name} → {dest_name}"
        + (f" ({country_name})" if country_name else "")
        + "\n"
        f"📅 Вылет: {date_formatted}\n"
        + (f"{stops_line}\n" if stops_line else "")
        + f"💰 {deal['current_price']:,} ₽  "
        f"(ваша цена: {deal['target_price']:,} ₽)\n"
        + drop_line
        + f"\n⚡ Цена может измениться — бронируйте быстрее!"
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
    _started_at = datetime.utcnow()
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

            # Семафор: не более 5 параллельных запросов (~200 req/min при avg 1.5 сек)
            _sem = asyncio.Semaphore(5)

            async def _fetch_route(o: str, dest: str, df: str | None, dt: str | None) -> list[dict]:
                async with _sem:
                    return await get_route_tickets(o, dest, df, dt)

            async def _fetch_country(o: str, cc: str, month: str) -> list[dict]:
                async with _sem:
                    return await get_route_tickets(o, cc, departure_month=month)

            for origin, subs in origin_subs.items():
                # --- Собираем уникальные ключи запросов ---

                # City-подписки с датами: (dest, date_from, date_to)
                city_keys: dict[tuple, tuple] = {}  # key → (dest, df, dt)
                for sub in subs:
                    if sub.dest_type == "city" and sub.date_from is not None:
                        key = (sub.dest_code, sub.date_from, sub.date_to)
                        city_keys[key] = (
                            sub.dest_code,
                            sub.date_from.isoformat(),
                            sub.date_to.isoformat(),
                        )

                # Country/region-подписки: (country_code, month_key)
                country_keys: dict[tuple, tuple] = {}  # key → (cc, month_key)
                for sub in subs:
                    if sub.dest_type == "country":
                        ccs = [sub.dest_code]
                    elif sub.dest_type == "region":
                        ccs = REGIONS.get(sub.dest_code, [])
                    else:
                        continue
                    month_key = sub.date_from.strftime("%Y-%m") if sub.date_from else ""
                    for cc in ccs:
                        k = (cc, month_key)
                        country_keys[k] = (cc, month_key)

                # --- Параллельные запросы ---
                city_coros = {k: _fetch_route(origin, v[0], v[1], v[2]) for k, v in city_keys.items()}
                country_coros = {k: _fetch_country(origin, v[0], v[1]) for k, v in country_keys.items()}

                city_results = dict(zip(
                    city_coros.keys(),
                    await asyncio.gather(*city_coros.values()),
                ))
                country_results = dict(zip(
                    country_coros.keys(),
                    await asyncio.gather(*country_coros.values()),
                ))

                # --- Собираем тикеты ---
                extra_tickets: list[dict] = []
                for sub in subs:
                    if sub.dest_type == "city" and sub.date_from is not None:
                        key = (sub.dest_code, sub.date_from, sub.date_to)
                        extra_tickets.extend(city_results.get(key, []))
                    elif sub.dest_type in ("country", "region"):
                        ccs = [sub.dest_code] if sub.dest_type == "country" else REGIONS.get(sub.dest_code, [])
                        month_key = sub.date_from.strftime("%Y-%m") if sub.date_from else ""
                        for cc in ccs:
                            extra_tickets.extend(country_results.get((cc, month_key), []))

                all_tickets = extra_tickets

                # Записать в price_history + собрать lookup stops/duration по route_key
                stops_lookup: dict[str, int | None] = {}
                layover_lookup: dict[str, int | None] = {}
                for ticket in all_tickets:
                    dest = ticket["destination_iata"]
                    departure = ticket["departure_at"]
                    if not dest or not departure:
                        continue
                    route_key = f"{origin}:{dest}:{departure}"
                    stops_lookup[route_key] = ticket.get("stops")
                    duration = ticket.get("duration")
                    duration_to = ticket.get("duration_to")
                    if duration is not None and duration_to is not None:
                        layover_lookup[route_key] = duration - duration_to
                    else:
                        layover_lookup[route_key] = None
                    await price_repo.add(
                        route_key=route_key,
                        price=ticket["price"],
                        ticket_link=ticket["ticket_link"],
                    )

                # Проверить подписки
                for sub in subs:
                    destinations = await resolve_destinations(sub, session)
                    # Фильтрация тикетов по дате, пересадкам и времени в пути
                    def _ticket_matches(t: dict) -> bool:
                        if sub.date_from is not None:
                            d = _parse_ticket_date(t["departure_at"])
                            if not (sub.date_from <= d <= sub.date_to):
                                return False
                        if sub.max_stops is not None:
                            stops = t.get("stops")
                            if stops is not None and stops > sub.max_stops:
                                return False
                        if sub.max_duration is not None:
                            duration = t.get("duration")
                            duration_to = t.get("duration_to")
                            if duration is not None and duration_to is not None:
                                layover = duration - duration_to
                                if layover > sub.max_duration:
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
                            deal["layover"] = layover_lookup.get(deal["route_key"])
                            # Проверяем пересадки и время пересадки у конкретного тикета из deal —
                            # analyzer мог вернуть более дешёвый рейс с лишними пересадками
                            if (
                                sub.max_stops is not None
                                and deal["stops"] is not None
                                and deal["stops"] > sub.max_stops
                            ):
                                continue
                            if (
                                sub.max_duration is not None
                                and deal["layover"] is not None
                                and deal["layover"] > sub.max_duration
                            ):
                                continue
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

            elapsed = (datetime.utcnow() - _started_at).total_seconds()
            logger.info(
                "Цикл мониторинга: завершён за %.1f сек. "
                "Проверено маршрутов: %d, найдено горящих: %d",
                elapsed,
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
    """Удаление старых записей price_history + деактивация устаревших подписок."""
    try:
        async with async_session() as session:
            price_repo = PriceHistoryRepository(session)
            deleted = await price_repo.delete_older_than(weeks=12)
            logger.info("Retention: удалено %d записей старше 12 недель", deleted)

            # Деактивируем подписки, у которых date_to уже прошла
            today = date.today()
            result = await session.execute(
                update(Subscription)
                .where(
                    Subscription.is_active.is_(True),
                    Subscription.date_to < today,
                )
                .values(is_active=False)
            )
            expired = result.rowcount
            await session.commit()
            if expired:
                logger.info("Retention: деактивировано %d устаревших подписок", expired)
    except Exception as e:
        logger.error("Ошибка retention job: %s", e)


async def build_stats_text(session: AsyncSession) -> str:
    """Собрать текст недельной статистики."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    active_users = (await session.execute(
        select(func.count()).select_from(User).where(User.is_active == True)  # noqa: E712
    )).scalar() or 0

    new_users = (await session.execute(
        select(func.count()).select_from(User).where(User.created_at >= week_ago)
    )).scalar() or 0

    notifications_sent = (await session.execute(
        select(func.count()).select_from(Notification).where(Notification.sent_at >= week_ago)
    )).scalar() or 0

    active_subs = (await session.execute(
        select(func.count()).select_from(Subscription).where(Subscription.is_active == True)  # noqa: E712
    )).scalar() or 0

    text = (
        "📊 Статистика за неделю\n\n"
        f"👥 Активных пользователей: {active_users}\n"
        f"🆕 Новых за неделю: {new_users}\n"
        f"📬 Уведомлений отправлено: {notifications_sent}\n"
        f"📋 Активных подписок: {active_subs}"
    )

    tp = await get_partner_stats(
        date_from=week_ago.strftime("%Y-%m-%d"),
        date_to=now.strftime("%Y-%m-%d"),
    )
    if tp is not None:
        text += (
            "\n\n✈️ Travelpayouts\n"
            f"🖱 Переходов: {tp['clicks']}\n"
            f"🎟 Бронирований: {tp['bookings']}\n"
            f"💶 Подтверждённый доход: {tp['paid_eur']} €\n"
            f"⏳ В обработке: {tp['processing_eur']} €"
        )

    return text


async def send_weekly_stats(bot: Bot) -> None:
    """Отправить недельную статистику всем администраторам."""
    if not ADMIN_IDS:
        return
    try:
        async with async_session() as session:
            text = await build_stats_text(session)
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.warning("Weekly stats: ошибка отправки admin=%d: %s", admin_id, e)

    except Exception as e:
        logger.error("Ошибка weekly stats job: %s", e)
