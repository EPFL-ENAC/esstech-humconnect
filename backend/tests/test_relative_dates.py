from datetime import UTC, datetime

from api.utils.relative_dates import (
    iso_date_to_utc_datetime,
    parse_iso_datetime,
    resolve_relative_datetime,
)


def test_parse_iso_datetime_defaults_naive_values_to_utc():
    assert parse_iso_datetime("2026-06-29T08:15:00").isoformat() == (
        "2026-06-29T08:15:00+00:00"
    )


def test_iso_date_to_utc_datetime_returns_midnight_utc():
    assert iso_date_to_utc_datetime("2026-06-29").isoformat() == (
        "2026-06-29T00:00:00+00:00"
    )


def test_resolve_relative_datetime_handles_calendar_and_clock_units():
    reference = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)

    assert resolve_relative_datetime(
        reference,
        direction="past",
        years=1,
        months=2,
        weeks=1,
        days=3,
        hours=4,
        minutes=5,
    ).isoformat() == "2025-04-19T07:55:00+00:00"


def test_resolve_relative_datetime_clamps_month_end_dates():
    reference = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)

    assert resolve_relative_datetime(
        reference,
        direction="past",
        months=1,
    ).isoformat() == "2026-02-28T12:00:00+00:00"
