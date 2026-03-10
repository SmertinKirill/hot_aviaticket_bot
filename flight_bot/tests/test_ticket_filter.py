"""Юнит-тесты для ticket_matches (фильтрация тикетов по параметрам подписки)."""

from datetime import date
from unittest.mock import MagicMock

from scheduler.tasks import ticket_matches


def _make_sub(
    date_from=None,
    date_to=None,
    max_stops=None,
    max_duration=None,
):
    sub = MagicMock()
    sub.date_from = date_from
    sub.date_to = date_to
    sub.max_stops = max_stops
    sub.max_duration = max_duration
    return sub


def _make_ticket(
    departure_at="2026-04-15T10:00:00",
    stops=0,
    duration=480,
    duration_to=420,
    destination_iata="BKK",
    price=8000,
):
    return {
        "departure_at": departure_at,
        "stops": stops,
        "duration": duration,
        "duration_to": duration_to,
        "destination_iata": destination_iata,
        "price": price,
    }


# --- Фильтр по дате ---

class TestDateFilter:
    def test_no_date_filter_passes(self):
        sub = _make_sub()
        t = _make_ticket()
        assert ticket_matches(sub, t) is True

    def test_date_in_range_passes(self):
        sub = _make_sub(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        t = _make_ticket(departure_at="2026-04-15T10:00:00")
        assert ticket_matches(sub, t) is True

    def test_date_before_range_fails(self):
        sub = _make_sub(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        t = _make_ticket(departure_at="2026-03-31T23:59:00")
        assert ticket_matches(sub, t) is False

    def test_date_after_range_fails(self):
        sub = _make_sub(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        t = _make_ticket(departure_at="2026-05-01T00:00:00")
        assert ticket_matches(sub, t) is False

    def test_boundary_date_from_passes(self):
        sub = _make_sub(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        t = _make_ticket(departure_at="2026-04-01T00:00:00")
        assert ticket_matches(sub, t) is True

    def test_boundary_date_to_passes(self):
        sub = _make_sub(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        t = _make_ticket(departure_at="2026-04-30T23:59:00")
        assert ticket_matches(sub, t) is True

    def test_invalid_departure_at_fails(self):
        sub = _make_sub(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
        t = _make_ticket(departure_at="bad-date")
        assert ticket_matches(sub, t) is False


# --- Фильтр по пересадкам ---

class TestStopsFilter:
    def test_no_stops_filter_passes(self):
        sub = _make_sub(max_stops=None)
        t = _make_ticket(stops=5)
        assert ticket_matches(sub, t) is True

    def test_stops_equal_max_passes(self):
        sub = _make_sub(max_stops=1)
        t = _make_ticket(stops=1)
        assert ticket_matches(sub, t) is True

    def test_stops_below_max_passes(self):
        sub = _make_sub(max_stops=2)
        t = _make_ticket(stops=0)
        assert ticket_matches(sub, t) is True

    def test_stops_above_max_fails(self):
        sub = _make_sub(max_stops=1)
        t = _make_ticket(stops=2)
        assert ticket_matches(sub, t) is False

    def test_stops_none_with_filter_fails(self):
        """Тикет с неизвестным числом пересадок (None) — отклоняем."""
        sub = _make_sub(max_stops=1)
        t = _make_ticket(stops=None)
        assert ticket_matches(sub, t) is False

    def test_direct_flight_max_stops_zero_passes(self):
        sub = _make_sub(max_stops=0)
        t = _make_ticket(stops=0)
        assert ticket_matches(sub, t) is True

    def test_one_stop_max_stops_zero_fails(self):
        sub = _make_sub(max_stops=0)
        t = _make_ticket(stops=1)
        assert ticket_matches(sub, t) is False


# --- Фильтр по длительности пересадки ---

class TestDurationFilter:
    def test_no_duration_filter_passes(self):
        sub = _make_sub(max_duration=None)
        t = _make_ticket(duration=600, duration_to=300)  # layover=300
        assert ticket_matches(sub, t) is True

    def test_layover_within_limit_passes(self):
        # duration=600, duration_to=420, layover=180 мин
        sub = _make_sub(max_duration=240)
        t = _make_ticket(duration=600, duration_to=420)
        assert ticket_matches(sub, t) is True

    def test_layover_equal_limit_passes(self):
        sub = _make_sub(max_duration=180)
        t = _make_ticket(duration=600, duration_to=420)  # layover=180
        assert ticket_matches(sub, t) is True

    def test_layover_exceeds_limit_fails(self):
        sub = _make_sub(max_duration=120)
        t = _make_ticket(duration=600, duration_to=420)  # layover=180
        assert ticket_matches(sub, t) is False

    def test_missing_duration_fields_passes(self):
        """Если duration/duration_to отсутствуют — пропускаем проверку."""
        sub = _make_sub(max_duration=120)
        t = _make_ticket()
        t["duration"] = None
        t["duration_to"] = None
        assert ticket_matches(sub, t) is True

    def test_partial_duration_fields_passes(self):
        """Если только одно поле отсутствует — пропускаем проверку."""
        sub = _make_sub(max_duration=120)
        t = _make_ticket()
        t["duration_to"] = None
        assert ticket_matches(sub, t) is True


# --- Комбинированные фильтры ---

class TestCombinedFilters:
    def test_all_filters_pass(self):
        sub = _make_sub(
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            max_stops=1,
            max_duration=480,
        )
        t = _make_ticket(
            departure_at="2026-04-15T10:00:00",
            stops=1,
            duration=900,
            duration_to=600,  # layover=300
        )
        assert ticket_matches(sub, t) is True

    def test_date_fails_others_pass(self):
        sub = _make_sub(
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            max_stops=1,
        )
        t = _make_ticket(departure_at="2026-05-01T10:00:00", stops=0)
        assert ticket_matches(sub, t) is False

    def test_stops_fails_others_pass(self):
        sub = _make_sub(
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            max_stops=0,
        )
        t = _make_ticket(departure_at="2026-04-15T10:00:00", stops=2)
        assert ticket_matches(sub, t) is False
