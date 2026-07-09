from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from api.utils.datetime_utils import parse_provider_datetime

ReliefWebRequestPayload = dict[str, Any]


class ReliefWebBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ReliefWebFilterCondition(ReliefWebBaseModel):
    field: str
    value: object


class ReliefWebDateFields(ReliefWebBaseModel):
    created: str | None = None
    original: str | None = None
    changed: str | None = None

    def first_datetime(self) -> datetime | None:
        for value in [self.created, self.original, self.changed]:
            parsed = parse_provider_datetime(value)
            if parsed is not None:
                return parsed
        return None


class ReliefWebNamedItem(ReliefWebBaseModel):
    name: str | None = None
    title: str | None = None

    def label(self, *, key: str = "name") -> str | None:
        value = getattr(self, key, None) or self.title
        return value if isinstance(value, str) and value else None


class ReliefWebItemFields(ReliefWebBaseModel):
    id: str | int | None = None
    title: str | None = None
    name: str | None = None
    url: str | None = None
    date: ReliefWebDateFields | None = None
    primary_country: ReliefWebNamedItem | list[ReliefWebNamedItem] | None = None
    source: list[str | ReliefWebNamedItem] | None = None
    disaster: list[str | ReliefWebNamedItem] | None = None
    disaster_type: list[str | ReliefWebNamedItem] | None = None
    primary_type: list[str | ReliefWebNamedItem] | None = None
    type: list[str | ReliefWebNamedItem] | None = None
    theme: list[str | ReliefWebNamedItem] | None = None
    format: list[str | ReliefWebNamedItem] | None = None
    status: str | None = None

    def title_or_name(self, fallback: str) -> str:
        return self.title or self.name or fallback

    def country_name(self, fallback: str) -> str:
        if isinstance(self.primary_country, list):
            country = self._first_string(self.primary_country)
            if country:
                return country

        if isinstance(self.primary_country, ReliefWebNamedItem):
            country = self.primary_country.label()
            if country:
                return country

        return fallback

    def created_datetime(self) -> datetime | None:
        return self.date.first_datetime() if self.date is not None else None

    def category(self, fallback: str) -> str:
        for values in [
            self.disaster_type,
            self.primary_type,
            self.type,
            self.theme,
            self.format,
            self.disaster,
        ]:
            value = self._first_string(values)
            if value:
                return value
        return fallback

    def source_names(self) -> list[str]:
        return self._string_list(self.source)

    def _first_string(
        self, values: Sequence[str | ReliefWebNamedItem] | None, *, key: str = "name"
    ) -> str | None:
        strings = self._string_list(values, key=key)
        return strings[0] if strings else None

    def _string_list(
        self, values: Sequence[str | ReliefWebNamedItem] | None, *, key: str = "name"
    ) -> list[str]:
        if values is None:
            return []

        output: list[str] = []
        for value in values:
            if isinstance(value, str) and value:
                output.append(value)
            elif isinstance(value, ReliefWebNamedItem):
                item = value.label(key=key)
                if item:
                    output.append(item)
        return output


class ReliefWebDataEntry(ReliefWebBaseModel):
    id: str | int | None = None
    fields: ReliefWebItemFields | None = None


class ReliefWebResponseBody(ReliefWebBaseModel):
    data: list[ReliefWebDataEntry] | None = None


class ReliefWebResponse(BaseModel):
    data: ReliefWebResponseBody
