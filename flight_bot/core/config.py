import os

from dotenv import load_dotenv

load_dotenv()

_REQUIRED = [
    "TELEGRAM_TOKEN",
    "TRAVELPAYOUTS_TOKEN",
    "TRAVELPAYOUTS_MARKER",
    "TRAVELPAYOUTS_TRS",
    "DATABASE_URL",
    "REDIS_URL",
]


def _get(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Переменная окружения {name} не задана. "
            f"Проверьте файл .env"
        )
    return value


TELEGRAM_TOKEN: str = _get("TELEGRAM_TOKEN")
TRAVELPAYOUTS_TOKEN: str = _get("TRAVELPAYOUTS_TOKEN")
TRAVELPAYOUTS_MARKER: str = _get("TRAVELPAYOUTS_MARKER")
TRAVELPAYOUTS_TRS: str = _get("TRAVELPAYOUTS_TRS")
DATABASE_URL: str = _get("DATABASE_URL")
REDIS_URL: str = _get("REDIS_URL")
ADMIN_IDS: list[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").strip("[] ").split(",") if x.strip()]

