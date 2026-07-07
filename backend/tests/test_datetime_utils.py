from datetime import UTC, datetime

from api.utils.datetime_utils import parse_provider_datetime, utc_isoformat_z


def test_parse_provider_datetime_accepts_zulu_iso_strings():
    assert parse_provider_datetime("2026-07-01T10:00:00Z") == datetime(
        2026, 7, 1, 10, 0, tzinfo=UTC
    )


def test_parse_provider_datetime_defaults_naive_values_to_utc():
    assert parse_provider_datetime("2026-07-01T10:00:00") == datetime(
        2026, 7, 1, 10, 0, tzinfo=UTC
    )


def test_parse_provider_datetime_normalizes_aware_values_to_utc():
    assert parse_provider_datetime("2026-07-01T12:00:00+02:00") == datetime(
        2026, 7, 1, 10, 0, tzinfo=UTC
    )


def test_parse_provider_datetime_accepts_epoch_milliseconds():
    assert parse_provider_datetime(1782900000000) == datetime(
        2026, 7, 1, 10, 0, tzinfo=UTC
    )


def test_parse_provider_datetime_returns_none_for_invalid_values():
    assert parse_provider_datetime(None) is None
    assert parse_provider_datetime("") is None
    assert parse_provider_datetime("not-a-date") is None


def test_utc_isoformat_z_formats_utc_datetimes_with_z():
    assert utc_isoformat_z(datetime(2026, 7, 1, 10, 0, tzinfo=UTC)) == (
        "2026-07-01T10:00:00Z"
    )


def test_utc_isoformat_z_returns_none_for_none():
    assert utc_isoformat_z(None) is None
