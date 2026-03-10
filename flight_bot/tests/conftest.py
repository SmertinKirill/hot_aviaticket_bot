"""Конфигурация pytest: маркеры и dummy env-переменные для unit-тестов."""

import os


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "smoke: интеграционные тесты, требующие реального окружения (.env, БД, Telegram).",
    )

    # Фиктивные значения для unit-тестов (не перезаписывают реальные из .env).
    # Без них core/config.py выбросит ValueError при импорте модулей.
    _defaults = {
        "TELEGRAM_TOKEN": "0:test_token_for_unit_tests",
        "TRAVELPAYOUTS_TOKEN": "test_tp_token",
        "TRAVELPAYOUTS_MARKER": "123456",
        "TRAVELPAYOUTS_TRS": "test_trs",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "REDIS_URL": "redis://localhost:6379",
    }
    for key, value in _defaults.items():
        os.environ.setdefault(key, value)
