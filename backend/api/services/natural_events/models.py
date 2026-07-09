from collections.abc import Mapping, Sequence
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.utils.datetime_utils import parse_provider_datetime, utc_isoformat_z

MAX_RADIUS_KM = 1000.0

RequestParamValue = str | int | float
RequestParams = Mapping[str, RequestParamValue]


class NaturalEventsBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class NaturalEventsStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NaturalEventsContextQuery(NaturalEventsStrictModel):
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=MAX_RADIUS_KM)


class NaturalEventsProviderCounts(BaseModel):
    nasa_eonet: int = 0
    usgs_earthquakes: int = 0


class NaturalEventsSummary(BaseModel):
    message: str
    counts: NaturalEventsProviderCounts


class NaturalEventsCenter(BaseModel):
    latitude: float
    longitude: float
    radius_km: float


class NaturalEventItem(BaseModel):
    provider: Literal["NASA EONET", "USGS Earthquake Catalog"]
    id: str
    title: str
    category: str | None = None
    time: str | None = None
    status: str
    latitude: float
    longitude: float
    distance_km: float
    magnitude: float | None = None
    source_url: str | None = None

    @classmethod
    def from_nasa_eonet_feature(
        cls,
        feature: "NasaEonetFeature",
        *,
        coordinate: "GeoCoordinate",
        distance_km: float,
    ) -> Self:
        properties = feature.properties
        event_time = parse_provider_datetime(properties.date)
        return cls(
            provider="NASA EONET",
            id=str(properties.id or feature.id or ""),
            title=properties.title or "Natural event",
            category=properties.category_titles(),
            time=utc_isoformat_z(event_time),
            status="closed" if properties.closed else "open",
            latitude=coordinate.latitude,
            longitude=coordinate.longitude,
            distance_km=round(distance_km, 1),
            magnitude=properties.magnitude_float(),
            source_url=properties.first_source_url(),
        )

    @classmethod
    def from_usgs_earthquake_feature(
        cls,
        feature: "UsgsEarthquakeFeature",
        *,
        distance_km: float,
    ) -> Self:
        properties = feature.properties
        coordinate = feature.geometry.coordinates
        event_time = parse_provider_datetime(properties.time)
        return cls(
            provider="USGS Earthquake Catalog",
            id=str(feature.id or properties.code or ""),
            title=properties.title or properties.place or "Earthquake",
            category=properties.type or "earthquake",
            time=utc_isoformat_z(event_time),
            status=properties.status or "",
            latitude=coordinate.latitude,
            longitude=coordinate.longitude,
            distance_km=round(distance_km, 1),
            magnitude=properties.mag,
            source_url=properties.url,
        )


class NaturalEventsContextResponse(BaseModel):
    summary: NaturalEventsSummary
    center: NaturalEventsCenter
    events: list[NaturalEventItem]
    warnings: list[str] | None = None


class GeoCoordinate(BaseModel):
    latitude: float
    longitude: float
    depth: float | None = None

    @classmethod
    def from_position(cls, values: object) -> Self | None:
        if not isinstance(values, Sequence) or isinstance(values, str):
            return None
        if len(values) < 2:
            return None

        longitude = cls._as_float(values[0])
        latitude = cls._as_float(values[1])
        depth = cls._as_float(values[2]) if len(values) > 2 else None
        if latitude is None or longitude is None:
            return None

        return cls(latitude=latitude, longitude=longitude, depth=depth)

    @staticmethod
    def _as_float(value: object) -> float | None:
        if not isinstance(value, int | float | str):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class GeoJsonPointGeometry(NaturalEventsBaseModel):
    type: Literal["Point"]
    coordinates: GeoCoordinate

    @field_validator("coordinates", mode="before")
    @classmethod
    def parse_coordinates(cls, value: object) -> GeoCoordinate | object:
        coordinate = GeoCoordinate.from_position(value)
        return coordinate if coordinate is not None else value

    def coordinate_list(self) -> list[GeoCoordinate]:
        return [self.coordinates]


class GeoJsonMultiPointGeometry(NaturalEventsBaseModel):
    type: Literal["MultiPoint"]
    coordinates: list[GeoCoordinate]

    @field_validator("coordinates", mode="before")
    @classmethod
    def parse_coordinates(cls, value: object) -> list[GeoCoordinate] | object:
        return coordinates_from_positions(value)

    def coordinate_list(self) -> list[GeoCoordinate]:
        return self.coordinates


class GeoJsonLineStringGeometry(NaturalEventsBaseModel):
    type: Literal["LineString"]
    coordinates: list[GeoCoordinate]

    @field_validator("coordinates", mode="before")
    @classmethod
    def parse_coordinates(cls, value: object) -> list[GeoCoordinate] | object:
        return coordinates_from_positions(value)

    def coordinate_list(self) -> list[GeoCoordinate]:
        return self.coordinates


class GeoJsonPolygonGeometry(NaturalEventsBaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[GeoCoordinate]]

    @field_validator("coordinates", mode="before")
    @classmethod
    def parse_coordinates(cls, value: object) -> list[list[GeoCoordinate]] | object:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return value

        rings: list[list[GeoCoordinate]] = []
        for ring in value:
            ring_coordinates = coordinates_from_positions(ring)
            if ring_coordinates:
                rings.append(ring_coordinates)

        return rings

    def coordinate_list(self) -> list[GeoCoordinate]:
        return [coordinate for ring in self.coordinates for coordinate in ring]


class GeoJsonMultiPolygonGeometry(NaturalEventsBaseModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[GeoCoordinate]]]

    @field_validator("coordinates", mode="before")
    @classmethod
    def parse_coordinates(
        cls, value: object
    ) -> list[list[list[GeoCoordinate]]] | object:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return value

        polygons: list[list[list[GeoCoordinate]]] = []
        for polygon in value:
            if not isinstance(polygon, Sequence) or isinstance(polygon, str):
                continue

            rings: list[list[GeoCoordinate]] = []
            for ring in polygon:
                ring_coordinates = coordinates_from_positions(ring)
                if ring_coordinates:
                    rings.append(ring_coordinates)

            if rings:
                polygons.append(rings)

        return polygons

    def coordinate_list(self) -> list[GeoCoordinate]:
        return [
            coordinate
            for polygon in self.coordinates
            for ring in polygon
            for coordinate in ring
        ]


GeoJsonGeometry = Annotated[
    GeoJsonPointGeometry
    | GeoJsonMultiPointGeometry
    | GeoJsonLineStringGeometry
    | GeoJsonPolygonGeometry
    | GeoJsonMultiPolygonGeometry,
    Field(discriminator="type"),
]


def coordinates_from_positions(value: object) -> list[GeoCoordinate]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []

    coordinates: list[GeoCoordinate] = []
    for item in value:
        coordinate = (
            item
            if isinstance(item, GeoCoordinate)
            else GeoCoordinate.from_position(item)
        )
        if coordinate is not None:
            coordinates.append(coordinate)

    return coordinates


class NasaEonetGeoJsonQueryParams(BaseModel):
    status: Literal["open", "closed", "all"] = "open"
    bbox: str
    limit: int = Field(gt=0)

    def to_request_params(self) -> RequestParams:
        return self.model_dump()


class NasaEonetCategory(NaturalEventsBaseModel):
    id: str | int | None = None
    title: str | None = None

    def label(self) -> str | None:
        value = self.title or self.id
        return str(value).strip() if value is not None and str(value).strip() else None


class NasaEonetSource(NaturalEventsBaseModel):
    id: str | None = None
    title: str | None = None
    source: str | None = None
    link: str | None = None
    url: str | None = None

    def url_or_link(self) -> str | None:
        for value in [self.url, self.link, self.source]:
            if value:
                return value
        return None


class NasaEonetProperties(NaturalEventsBaseModel):
    id: str | int | None = None
    title: str | None = None
    description: str | None = None
    link: str | None = None
    closed: str | None = None
    date: str | int | float | None = None
    magnitudeValue: str | int | float | None = None
    magnitudeUnit: str | None = None
    magnitudeDescription: str | None = None
    categories: list[NasaEonetCategory] | None = None
    sources: list[NasaEonetSource] | None = None
    geometryDates: list[str] | None = None

    def category_titles(self) -> str | None:
        if self.categories is None:
            return None

        titles = [title for category in self.categories if (title := category.label())]
        return ", ".join(titles) or None

    def first_source_url(self) -> str | None:
        if self.link:
            return self.link
        if self.sources is None:
            return None

        for source in self.sources:
            source_url = source.url_or_link()
            if source_url:
                return source_url

        return None

    def magnitude_float(self) -> float | None:
        return GeoCoordinate._as_float(self.magnitudeValue)


class NasaEonetFeature(NaturalEventsBaseModel):
    type: str | None = None
    id: str | int | None = None
    properties: NasaEonetProperties
    geometry: GeoJsonGeometry


class NasaEonetGeoJsonResponse(NaturalEventsBaseModel):
    type: str | None = None
    features: list[NasaEonetFeature]


class UsgsEarthquakeGeoJsonQueryParams(BaseModel):
    format: Literal["geojson"] = "geojson"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    maxradiuskm: float = Field(gt=0, le=20001.6)
    starttime: date
    endtime: date
    orderby: Literal["time", "time-asc", "magnitude", "magnitude-asc"] = "time"
    limit: int = Field(gt=0, le=20000)

    def to_request_params(self) -> RequestParams:
        return {
            "format": self.format,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "maxradiuskm": self.maxradiuskm,
            "starttime": self.starttime.isoformat(),
            "endtime": self.endtime.isoformat(),
            "orderby": self.orderby,
            "limit": self.limit,
        }


class UsgsEarthquakeMetadata(NaturalEventsBaseModel):
    generated: int | None = None
    url: str | None = None
    title: str | None = None
    api: str | None = None
    count: int | None = None
    status: int | None = None


class UsgsEarthquakeProperties(NaturalEventsBaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    mag: float | None = None
    place: str | None = None
    title: str | None = None
    time: int | str | None = None
    updated: int | str | None = None
    tz: int | None = None
    url: str | None = None
    detail: str | None = None
    felt: int | None = None
    cdi: float | None = None
    mmi: float | None = None
    alert: str | None = None
    status: str | None = None
    tsunami: int | None = None
    sig: int | None = None
    net: str | None = None
    code: str | None = None
    ids: str | None = None
    sources: str | None = None
    types: str | None = None
    nst: int | None = None
    dmin: float | None = None
    rms: float | None = None
    gap: float | None = None
    mag_type: str | None = Field(default=None, alias="magType")
    type: str | None = None


class UsgsEarthquakeFeature(NaturalEventsBaseModel):
    type: Literal["Feature"] | None = None
    properties: UsgsEarthquakeProperties
    geometry: GeoJsonPointGeometry
    id: str | None = None


class UsgsEarthquakeGeoJsonResponse(NaturalEventsBaseModel):
    type: Literal["FeatureCollection"] | None = None
    metadata: UsgsEarthquakeMetadata | None = None
    bbox: list[float] | None = None
    features: list[UsgsEarthquakeFeature]


class NaturalEventSortKey(BaseModel):
    magnitude: float
    timestamp: float

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, NaturalEventSortKey):
            return NotImplemented
        if self.magnitude != other.magnitude:
            return self.magnitude < other.magnitude
        return self.timestamp < other.timestamp


def event_sort_key(item: NaturalEventItem) -> NaturalEventSortKey:
    event_time = parse_provider_datetime(item.time)
    magnitude = item.magnitude if item.magnitude is not None else -1.0
    timestamp = event_time.timestamp() if event_time is not None else 0.0
    return NaturalEventSortKey(magnitude=magnitude, timestamp=timestamp)
