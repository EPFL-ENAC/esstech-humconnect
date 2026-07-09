import math

EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bbox_for_radius(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> str:
    latitude_delta = math.degrees(radius_km / EARTH_RADIUS_KM)
    cos_latitude = math.cos(math.radians(latitude))
    longitude_delta = (
        180.0 if abs(cos_latitude) < 1e-12 else latitude_delta / cos_latitude
    )

    min_latitude = max(-90.0, latitude - latitude_delta)
    max_latitude = min(90.0, latitude + latitude_delta)
    min_longitude = max(-180.0, longitude - longitude_delta)
    max_longitude = min(180.0, longitude + longitude_delta)

    return (
        f"{min_longitude:.6f},{max_latitude:.6f},{max_longitude:.6f},{min_latitude:.6f}"
    )


def coordinate_pairs_from_geojson_coordinates(
    coordinates: object,
) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []

    def collect(value: object) -> None:
        if not isinstance(value, list):
            return

        if len(value) >= 2:
            longitude = as_float(value[0])
            latitude = as_float(value[1])
            if longitude is not None and latitude is not None:
                pairs.append((latitude, longitude))
                return

        for item in value:
            collect(item)

    collect(coordinates)
    return pairs


def as_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
