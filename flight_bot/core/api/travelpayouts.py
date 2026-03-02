import asyncio
import logging

import httpx

from core.api import cache
from core.config import TRAVELPAYOUTS_TOKEN

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.travelpayouts.com/graphql/v1/query"
LATEST_PRICES_URL = "https://api.travelpayouts.com/v2/prices/latest"

_RETRY_DELAYS = [1, 2, 4]


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
                result.append(
                    {
                        "destination_iata": dest,
                        "price": int(p.get("value", 0)),
                        "departure_at": (p.get("departure_at") or "")[:10],
                        "stops": p.get("number_of_changes"),
                        "ticket_link": p.get("ticket_link", ""),
                    }
                )
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
