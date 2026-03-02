"""Логика определения горящего билета."""

import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession

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

    Уведомляем если current_price <= subscription.target_price.
    Возвращает dict с данными для уведомления или None.
    """
    target_price = subscription.target_price
    if not target_price or target_price <= 0:
        return None

    price_repo = PriceHistoryRepository(session)
    notif_repo = NotificationRepository(session)

    prefix = f"{origin_iata}:{dest_iata}:"
    latest = await price_repo.get_latest_by_prefix(
        prefix,
        date_from=subscription.date_from,
        date_to=subscription.date_to,
    )

    if latest is None:
        return None

    route_key = latest.route_key
    current_price = latest.price
    ticket_link = latest.ticket_link

    if current_price > target_price:
        return None

    # Антиспам: не слать чаще раза в сутки по одному маршруту,
    # и только если цена стала ещё ниже чем при прошлом уведомлении
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
        "target_price": target_price,
        "ticket_link": _ensure_marker(ticket_link),
    }
