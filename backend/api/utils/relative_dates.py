from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

RelativeDateDirection = Literal["past", "future"]


def current_datetime() -> datetime:
    return datetime.now(UTC)


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def iso_date_to_utc_datetime(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)


def add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def resolve_relative_datetime(
    reference: datetime,
    *,
    direction: RelativeDateDirection,
    years: int | None = None,
    months: int | None = None,
    weeks: int | None = None,
    days: int | None = None,
    hours: int | None = None,
    minutes: int | None = None,
) -> datetime:
    sign = -1 if direction == "past" else 1
    resolved = add_calendar_months(
        reference,
        sign * (((years or 0) * 12) + (months or 0)),
    )
    return resolved + timedelta(
        weeks=sign * (weeks or 0),
        days=sign * (days or 0),
        hours=sign * (hours or 0),
        minutes=sign * (minutes or 0),
    )
