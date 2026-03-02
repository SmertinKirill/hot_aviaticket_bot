"""Загрузка справочников стран, городов и аэропортов из Travelpayouts."""

import asyncio
import logging

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from core.db.base import async_session
from core.db.models import Airport, City, Country

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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

COUNTRIES_URL = "https://api.travelpayouts.com/data/ru/countries.json"
CITIES_URL = "https://api.travelpayouts.com/data/ru/cities.json"
AIRPORTS_URL = "https://api.travelpayouts.com/data/ru/airports.json"


def _country_code_to_region(code: str) -> str | None:
    for region, codes in REGIONS.items():
        if code in codes:
            return region
    return None


BATCH_SIZE = 500


async def _upsert_batched(session, model, rows, index_elements, update_fields):
    """INSERT ... ON CONFLICT DO UPDATE батчами по BATCH_SIZE."""
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        stmt = insert(model).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={f: getattr(stmt.excluded, f) for f in update_fields},
        )
        await session.execute(stmt)
    await session.commit()


async def load() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        logger.info("Загрузка справочников из Travelpayouts...")
        countries_resp = await client.get(COUNTRIES_URL)
        countries_resp.raise_for_status()
        countries_data = countries_resp.json()

        cities_resp = await client.get(CITIES_URL)
        cities_resp.raise_for_status()
        cities_data = cities_resp.json()

        airports_resp = await client.get(AIRPORTS_URL)
        airports_resp.raise_for_status()
        airports_data = airports_resp.json()

    async with async_session() as session:
        # --- Страны ---
        country_rows = []
        for c in countries_data:
            code = c.get("code")
            if not code:
                continue
            country_rows.append(
                {
                    "code": code,
                    "name_ru": c.get("name", "") or "",
                    "name_en": c.get("name_translations", {}).get("en", "") or "",
                    "region": _country_code_to_region(code),
                }
            )

        if country_rows:
            await _upsert_batched(
                session, Country, country_rows,
                ["code"], ["name_ru", "name_en", "region"],
            )
        logger.info("Страны: обработано %d записей", len(country_rows))

        # --- Города ---
        existing_countries = {r["code"] for r in country_rows}

        city_rows = []
        for c in cities_data:
            iata = c.get("code")
            if not iata:
                continue
            country_code = c.get("country_code")
            if not country_code or country_code not in existing_countries:
                continue
            city_rows.append(
                {
                    "iata": iata,
                    "name_ru": c.get("name", "") or "",
                    "name_en": c.get("name_translations", {}).get("en", "") or "",
                    "country_code": country_code,
                }
            )

        if city_rows:
            await _upsert_batched(
                session, City, city_rows,
                ["iata"], ["name_ru", "name_en", "country_code"],
            )
        logger.info("Города: обработано %d записей", len(city_rows))

        # --- Аэропорты ---
        existing_cities = {r["iata"] for r in city_rows}

        airport_rows = []
        for a in airports_data:
            iata = a.get("code")
            if not iata:
                continue
            city_iata = a.get("city_code")
            country_code = a.get("country_code")
            if not city_iata or city_iata not in existing_cities:
                continue
            if not country_code or country_code not in existing_countries:
                continue
            airport_rows.append(
                {
                    "iata": iata,
                    "name_ru": a.get("name", "") or "",
                    "name_en": a.get("name_translations", {}).get("en", "") or "",
                    "city_iata": city_iata,
                    "country_code": country_code,
                }
            )

        if airport_rows:
            await _upsert_batched(
                session, Airport, airport_rows,
                ["iata"], ["name_ru", "name_en", "city_iata", "country_code"],
            )
        logger.info("Аэропорты: обработано %d записей", len(airport_rows))

    logger.info("Загрузка справочников завершена")


async def is_empty() -> bool:
    """Проверить, пуста ли таблица countries."""
    async with async_session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM countries"))
        count = result.scalar_one()
        return count == 0


async def load_if_empty() -> None:
    """Загрузить справочники если таблица countries пуста."""
    try:
        if await is_empty():
            logger.info("Таблица countries пуста, загружаем справочники...")
            await load()
    except Exception as e:
        logger.warning("Не удалось проверить/загрузить справочники: %s", e)


if __name__ == "__main__":
    asyncio.run(load())
