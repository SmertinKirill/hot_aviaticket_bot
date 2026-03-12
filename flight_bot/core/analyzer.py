"""Логика определения горящего билета."""

import logging
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories.notification_repo import NotificationRepository

logger = logging.getLogger(__name__)

_AVIASALES_BASE = "https://www.aviasales.ru"


def _build_ticket_url(ticket_link: str, route_key: str) -> str:
    """Собрать ссылку в формате Aviasales: /search/MOW1503BKK1?t=...

    Открывает страницу поиска и автоматически показывает конкретный билет.
    Если ticket_link недоступен — возвращает базовую поисковую ссылку.
    Marker не добавляется — трекинг идёт через Travelpayouts Links API.
    """
    if ticket_link:
        try:
            parsed = urlparse(ticket_link)
            path = parsed.path.lstrip("/")
            if not path.startswith("search/"):
                path = f"search/{path}"
            search_path = f"/{path}"
            params = parse_qs(parsed.query, keep_blank_values=True)
            query = urlencode({k: v[0] for k, v in params.items()})
            return f"{_AVIASALES_BASE}{search_path}?{query}" if query else f"{_AVIASALES_BASE}{search_path}"
        except Exception:
            pass

    try:
        origin, dest, date_str = route_key.split(":")
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_part = dt.strftime("%d%m")
        return f"{_AVIASALES_BASE}/search/{origin}{date_part}{dest}1"
    except Exception:
        return _AVIASALES_BASE


async def check(
    subscription,
    origin_iata: str,
    dest_iata: str,
    current_price: int,
    ticket_link: str,
    route_key: str,
    cooldown_key: str,
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

    if current_price > target_price:
        return None

    _SIGNIFICANT_DROP = {"RUB": 100, "USD": 1, "EUR": 1}

    notif_repo = NotificationRepository(session)
    last_notif = await notif_repo.get_last(subscription.id, cooldown_key)
    if last_notif:
        elapsed = datetime.utcnow() - last_notif.sent_at
        if elapsed < timedelta(hours=24):
            currency = (subscription.currency or "RUB").upper()
            threshold = _SIGNIFICANT_DROP.get(currency, 100)
            drop = last_notif.price - current_price
            if drop < threshold:
                return None
        elif current_price >= last_notif.price and elapsed < timedelta(days=7):
            return None

    return {
        "subscription_id": subscription.id,
        "route_key": route_key,
        "origin_iata": origin_iata,
        "dest_iata": dest_iata,
        "current_price": current_price,
        "target_price": target_price,
        "ticket_link": _build_ticket_url(ticket_link, route_key),
        "prev_price": last_notif.price if last_notif else None,
    }
