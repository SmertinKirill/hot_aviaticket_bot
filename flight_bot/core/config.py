import os

from dotenv import load_dotenv

load_dotenv()

_REQUIRED = [
    "TELEGRAM_TOKEN",
    "TRAVELPAYOUTS_TOKEN",
    "TRAVELPAYOUTS_MARKER",
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
DATABASE_URL: str = _get("DATABASE_URL")
REDIS_URL: str = _get("REDIS_URL")
