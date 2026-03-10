"""Юнит-тесты для парсинга дат в боте."""

from datetime import date

from bot.handlers.subscriptions import _parse_date_range, _parse_single_date


class TestParseSingleDate:
    def test_dd_mm_yyyy(self):
        assert _parse_single_date("15.04.2026") == date(2026, 4, 15)

    def test_dd_slash_mm_yyyy(self):
        assert _parse_single_date("15/04/2026") == date(2026, 4, 15)

    def test_short_year_dot(self):
        assert _parse_single_date("15.04.26") == date(2026, 4, 15)

    def test_short_year_slash(self):
        assert _parse_single_date("15/04/26") == date(2026, 4, 15)

    def test_invalid_text(self):
        assert _parse_single_date("invalid") is None

    def test_invalid_day(self):
        assert _parse_single_date("32.04.2026") is None

    def test_invalid_month(self):
        assert _parse_single_date("15.13.2026") is None

    def test_whitespace_stripped(self):
        assert _parse_single_date("  15.04.2026  ") == date(2026, 4, 15)


class TestParseDateRange:
    def test_dash_separator(self):
        result = _parse_date_range("01.04.2026 - 30.04.2026")
        assert result == (date(2026, 4, 1), date(2026, 4, 30))

    def test_emdash_separator(self):
        result = _parse_date_range("01.04.2026 — 30.04.2026")
        assert result == (date(2026, 4, 1), date(2026, 4, 30))

    def test_reversed_dates_normalized(self):
        result = _parse_date_range("30.04.2026 - 01.04.2026")
        assert result == (date(2026, 4, 1), date(2026, 4, 30))

    def test_short_year_in_range(self):
        result = _parse_date_range("01.04.26 - 30.04.26")
        assert result == (date(2026, 4, 1), date(2026, 4, 30))

    def test_invalid_returns_none(self):
        assert _parse_date_range("invalid") is None

    def test_single_date_returns_none(self):
        assert _parse_date_range("15.04.2026") is None
