"""Логика определения горящего билета."""

import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession

from core.api.travelpayouts import get_global_min_price
from core.config import TRAVELPAYOUTS_MARKER
from core.db.repositories.notification_repo import NotificationRepository
from core.db.repositories.price_history_repo import PriceHistoryRepository

logger = logging.getLogger(__name__)


def _ensure_marker(ticket_link: str) -> str:
    """Добавить маркер партнёрки если его нет."""
    if not ticket_link:
        return ticket_link
    if "marker" in ticket_link:
        return ticket_link
    if "?" in ticket_link:
        return f"{ticket_link}&marker={TRAVELPAYOUTS_MARKER}"
    return f"{ticket_link}?marker={TRAVELPAYOUTS_MARKER}"


async def check(
    subscription,
    origin_iata: str,
    dest_iata: str,
    session: AsyncSession,
) -> dict | None:
    """
    Проверить, является ли текущая цена горящей для маршрута.

    Возвращает dict с данными для уведомления или None.
    """
    price_repo = PriceHistoryRepository(session)
    notif_repo = NotificationRepository(session)

    prefix = f"{origin_iata}:{dest_iata}:"
    latest = await price_repo.get_latest_by_prefix(prefix)

    if latest is None:
        return None

    route_key = latest.route_key
    current_price = latest.price
    ticket_link = latest.ticket_link

    # Определяем базовую цену для сравнения
    count = await price_repo.get_count(route_key, weeks=8)
    avg = await price_repo.get_avg_price(route_key, weeks=8)

    if count < 5:
        global_min = await get_global_min_price(origin_iata, dest_iata)
        if global_min is None:
            return None
        base_price = global_min
    else:
        base_price = avg

    if base_price is None or base_price <= 0:
        return None

    discount_pct = round((base_price - current_price) / base_price * 100)

    if discount_pct < subscription.user.threshold_pct:
        return None

    # Антиспам — проверка на уровне подписки
    last_notif = await notif_repo.get_last(subscription.id, route_key)
    if last_notif:
        if datetime.utcnow() - last_notif.sent_at < timedelta(hours=24):
            return None
        if current_price >= last_notif.price:
            return None

    return {
        "subscription_id": subscription.id,
        "route_key": route_key,
        "origin_iata": origin_iata,
        "dest_iata": dest_iata,
        "current_price": current_price,
        "base_price": int(base_price),
        "discount_pct": discount_pct,
        "ticket_link": _ensure_marker(ticket_link),
    }
