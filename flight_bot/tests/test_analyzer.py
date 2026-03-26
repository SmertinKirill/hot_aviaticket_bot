"""Юнит-тесты для core/analyzer.py."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core import analyzer


def _make_sub(target_price: int = 10_000, sub_id: int = 1, currency: str = "RUB"):
    sub = MagicMock()
    sub.id = sub_id
    sub.target_price = target_price
    sub.currency = currency
    return sub


def _make_notif(price: int, hours_ago: int):
    notif = MagicMock()
    notif.price = price
    notif.sent_at = datetime.utcnow() - timedelta(hours=hours_ago)
    return notif


@pytest.fixture
def mock_notif_repo():
    with patch("core.analyzer.NotificationRepository") as MockRepo:
        repo = AsyncMock()
        MockRepo.return_value = repo
        yield repo


async def test_price_above_target_returns_none(mock_notif_repo):
    sub = _make_sub(target_price=10_000)
    result = await analyzer.check(sub, "MOW", "BKK", 12_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is None


async def test_zero_target_price_returns_none(mock_notif_repo):
    sub = _make_sub(target_price=0)
    result = await analyzer.check(sub, "MOW", "BKK", 5_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is None


async def test_first_notification_returns_deal(mock_notif_repo):
    mock_notif_repo.get_last.return_value = None
    sub = _make_sub(target_price=10_000)

    result = await analyzer.check(sub, "MOW", "BKK", 8_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())

    assert result is not None
    assert result["current_price"] == 8_000
    assert result["target_price"] == 10_000
    assert result["prev_price"] is None
    assert result["origin_iata"] == "MOW"
    assert result["dest_iata"] == "BKK"


async def test_cooldown_24h_blocks_insignificant_drop(mock_notif_repo):
    """Менее 24 ч, падение < 100 ₽ — блокируется."""
    mock_notif_repo.get_last.return_value = _make_notif(price=8_050, hours_ago=12)
    sub = _make_sub(target_price=10_000)

    result = await analyzer.check(sub, "MOW", "BKK", 8_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is None


async def test_cooldown_24h_allows_significant_drop(mock_notif_repo):
    """Менее 24 ч, но падение >= 100 ₽ — отправляем."""
    mock_notif_repo.get_last.return_value = _make_notif(price=9_000, hours_ago=12)
    sub = _make_sub(target_price=10_000)

    result = await analyzer.check(sub, "MOW", "BKK", 8_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is not None
    assert result["prev_price"] == 9_000


async def test_same_price_after_24h_blocked_within_3d(mock_notif_repo):
    """Цена не снизилась, прошло 48 часов, но меньше 3 дней — не отправляем."""
    mock_notif_repo.get_last.return_value = _make_notif(price=8_000, hours_ago=48)
    sub = _make_sub(target_price=10_000)

    result = await analyzer.check(sub, "MOW", "BKK", 8_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is None


async def test_lower_price_after_24h_allowed(mock_notif_repo):
    """Цена снизилась после 24 часов — отправляем, prev_price заполнен."""
    mock_notif_repo.get_last.return_value = _make_notif(price=9_000, hours_ago=48)
    sub = _make_sub(target_price=10_000)

    result = await analyzer.check(sub, "MOW", "BKK", 7_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())

    assert result is not None
    assert result["prev_price"] == 9_000


async def test_resend_after_3_days_same_price(mock_notif_repo):
    """Прошло более 3 дней — отправляем даже если цена не изменилась."""
    mock_notif_repo.get_last.return_value = _make_notif(price=8_000, hours_ago=3 * 24 + 1)
    sub = _make_sub(target_price=10_000)

    result = await analyzer.check(sub, "MOW", "BKK", 8_000, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is not None


async def test_cooldown_24h_usd_threshold(mock_notif_repo):
    """Для USD порог значительного падения — $1."""
    mock_notif_repo.get_last.return_value = _make_notif(price=300, hours_ago=12)
    sub = _make_sub(target_price=500, currency="USD")

    # Падение $0 — блокируется
    result = await analyzer.check(sub, "MOW", "BKK", 300, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is None

    # Падение $1 — отправляем
    result = await analyzer.check(sub, "MOW", "BKK", 299, "", "MOW:BKK:2026-04-01", "MOW:BKK", AsyncMock())
    assert result is not None


def test_build_ticket_url_rest_link():
    url = analyzer._build_ticket_url("/search/MOW1504BKK1?t=ABC123", "MOW:BKK:2026-04-15")
    assert "aviasales.ru" in url
    assert "MOW" in url


def test_build_ticket_url_fallback_from_route_key():
    url = analyzer._build_ticket_url("", "MOW:BKK:2026-04-15")
    assert "aviasales.ru" in url
    assert "MOW" in url
    assert "BKK" in url
