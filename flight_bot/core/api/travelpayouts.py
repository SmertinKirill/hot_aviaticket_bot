import asyncio
import logging

import httpx

from core.api import cache
from core.config import TRAVELPAYOUTS_MARKER, TRAVELPAYOUTS_TOKEN, TRAVELPAYOUTS_TRS

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.travelpayouts.com/graphql/v1/query"
REST_PRICES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
LINKS_URL = "https://api.travelpayouts.com/links/v1/create"
STATS_URL = "https://api.travelpayouts.com/statistics/v1/execute_query"

_RETRY_DELAYS = [1, 2, 4]


async def shorten_link(url: str) -> str:
    """Конвертировать URL в короткую партнёрскую ссылку через Travelpayouts Links API.

    Возвращает partner_url (напр. https://aviasales.tp.st/XXXXX?erid=...)
    или исходный url при любой ошибке.
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                LINKS_URL,
                json={
                    "trs": int(TRAVELPAYOUTS_TRS),
                    "marker": int(TRAVELPAYOUTS_MARKER),
                    "shorten": True,
                    "links": [{"url": url}],
                },
                headers={"X-Access-Token": TRAVELPAYOUTS_TOKEN},
            )
            if not resp.is_success:
                logger.warning("shorten_link %d: %s", resp.status_code, resp.text)
                return url
            data = resp.json()
        partner_url = data["result"]["links"][0]["partner_url"]
        return f"{partner_url}?sub_id=1"
    except Exception as e:
        logger.warning("shorten_link ошибка, fallback на исходный URL: %s", e)
    return url


async def get_cheap_tickets(origin_iata: str) -> list[dict]:
    """Получить дешёвые билеты из origin через GraphQL API."""
    query = """
    {
      prices_one_way(
        params: { origin: "%s" }
        grouping: DIRECTIONS
        paging: { offset: 0 limit: 100 }
        sorting: VALUE_ASC
      ) {
        destination_city_iata
        departure_at
        value
        trip_duration
        number_of_changes
        ticket_link
      }
    }
    """ % origin_iata

    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    GRAPHQL_URL,
                    json={"query": query},
                    headers={"X-Access-Token": TRAVELPAYOUTS_TOKEN},
                )
                resp.raise_for_status()
                data = resp.json()

            prices = data.get("data", {}).get("prices_one_way") or []
            result = []
            for p in prices:
                dest = p.get("destination_city_iata")
                if not dest:
                    continue
                # Пропускаем поезда: у них в ticket_link хэш начинается с R
                # и содержит коды ж/д станций (ZKD, ZLK и т.д.)
                link = p.get("ticket_link") or ""
                link_hash = link.lstrip("/").split("?")[0]  # MOW1703LED1
                t_param = ""
                if "?t=" in link:
                    t_param = link.split("?t=")[1].split("&")[0]
                if t_param.startswith("R"):  # Railway
                    continue
                result.append(
                    {
                        "destination_iata": dest,
                        "price": int(p.get("value", 0)),
                        "departure_at": (p.get("departure_at") or "")[:10],
                        "stops": p.get("number_of_changes"),
                        "ticket_link": p.get("ticket_link", ""),
                    }
                )
            logger.info("get_cheap_tickets(%s): %d билетов", origin_iata, len(result))
            return result

        except Exception as e:
            logger.error(
                "Travelpayouts GraphQL ошибка (попытка %d/%d): %s",
                attempt + 1,
                len(_RETRY_DELAYS),
                e,
            )
            if attempt < len(_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)

    logger.error(
        "Travelpayouts GraphQL: все попытки исчерпаны для origin=%s",
        origin_iata,
    )
    return []


async def get_route_tickets(
    origin_iata: str,
    destination_iata: str,
    date_from: str | None = None,
    date_to: str | None = None,
    departure_month: str | None = None,
) -> list[dict]:
    """Получить билеты для конкретного маршрута с фильтрацией по датам.

    departure_month (YYYY-MM) — передаётся в API для фильтрации на стороне сервера.
    Используется для country/region подписок чтобы получить рейсы в нужный месяц,
    а не только ближайшие 100 дешёвых.
    date_from / date_to — дополнительная клиентская фильтрация.
    REST /v3/prices_for_dates: лимит 600 req/min.
    """
    params = {
        "origin": origin_iata,
        "destination": destination_iata,
        "one_way": "true",
        "currency": "rub",
        "sorting": "price",
        "limit": 100,
    }
    if departure_month:
        params["departure_at"] = departure_month

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                REST_PRICES_URL,
                params=params,
                headers={"X-Access-Token": TRAVELPAYOUTS_TOKEN},
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("data") or []

        if date_from or date_to:
            rows = [
                r for r in rows
                if (not date_from or (r.get("departure_at") or "")[:10] >= date_from)
                and (not date_to or (r.get("departure_at") or "")[:10] <= date_to)
            ]

        result = []
        for r in rows:
            if not r.get("price", 0):
                continue
            link = r.get("link") or ""
            t_param = link.split("?t=")[1].split("&")[0] if "?t=" in link else ""
            if t_param.startswith("R"):  # Railway — пропускаем
                continue
            result.append({
                "destination_iata": r.get("destination", destination_iata),
                "price": int(r["price"]),
                "departure_at": (r.get("departure_at") or "")[:10],
                "stops": r.get("transfers"),
                "duration": r.get("duration"),     # минуты, полное время (полёт + пересадки)
                "duration_to": r.get("duration_to"),  # минуты, только время в воздухе
                "ticket_link": link,
            })
        logger.info("get_route_tickets(%s→%s): %d билетов", origin_iata, destination_iata, len(result))
        return result

    except Exception as e:
        logger.error(
            "get_route_tickets %s→%s: %s: %s", origin_iata, destination_iata, type(e).__name__, e
        )
        return []


async def get_partner_stats(date_from: str, date_to: str) -> dict | None:
    """Получить статистику партнёра за период.

    date_from / date_to — строки YYYY-MM-DD.
    Возвращает dict с ключами clicks, bookings, paid_eur, processing_eur
    или None при ошибке.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                STATS_URL,
                json={
                    "fields": [
                        "redirects_count",
                        "processing_actions_count",
                        "paid_actions_count",
                        "paid_profit_eur_sum",
                        "processing_profit_eur_sum",
                    ],
                    "filters": [
                        {"field": "date", "op": "ge", "value": date_from},
                        {"field": "date", "op": "le", "value": date_to},
                    ],
                },
                headers={"X-Access-Token": TRAVELPAYOUTS_TOKEN},
            )
            if not resp.is_success:
                logger.warning("partner_stats %d: %s", resp.status_code, resp.text)
                return None
            data = resp.json()

        rows = data if isinstance(data, list) else data.get("results", data.get("data", []))
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        return {
            "clicks": int(row.get("redirects_count") or 0),
            "bookings": int((row.get("processing_actions_count") or 0) + (row.get("paid_actions_count") or 0)),
            "paid_eur": round(float(row.get("paid_profit_eur_sum") or 0), 2),
            "processing_eur": round(float(row.get("processing_profit_eur_sum") or 0), 2),
        }
    except Exception as e:
        logger.warning("partner_stats ошибка: %s", e)
        return None


async def get_global_min_price(
    origin_iata: str,
    destination_iata: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int | None:
    """Получить минимальную цену для конкретного маршрута через GraphQL.

    date_from / date_to — ISO строки YYYY-MM-DD для фильтрации по датам.
    """
    cache_key_suffix = f"{date_from or ''}:{date_to or ''}"
    cached = await cache.get_global_min(
        origin_iata, f"{destination_iata}:{cache_key_suffix}"
    )
    if cached is not None:
        return cached

    query = """
    {
      prices_one_way(
        params: { origin: "%s", destination: "%s" }
        grouping: DATES
        paging: { offset: 0 limit: 200 }
        sorting: VALUE_ASC
      ) {
        departure_at
        value
      }
    }
    """ % (origin_iata, destination_iata)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GRAPHQL_URL,
                json={"query": query},
                headers={"X-Access-Token": TRAVELPAYOUTS_TOKEN},
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("data", {}).get("prices_one_way") or []
        if not rows:
            return None

        # Фильтрация по датам если задан диапазон
        if date_from or date_to:
            filtered = []
            for r in rows:
                dep = (r.get("departure_at") or "")[:10]
                if date_from and dep < date_from:
                    continue
                if date_to and dep > date_to:
                    continue
                filtered.append(r)
            rows = filtered

        if not rows:
            return None

        min_price = min(
            int(r.get("value", 0)) for r in rows if r.get("value", 0) > 0
        )
        if min_price > 0:
            await cache.set_global_min(
                origin_iata, f"{destination_iata}:{cache_key_suffix}", min_price
            )
            return min_price

        return None

    except Exception as e:
        logger.error(
            "Global min ошибка для %s→%s: %s",
            origin_iata,
            destination_iata,
            e,
        )
        return None
