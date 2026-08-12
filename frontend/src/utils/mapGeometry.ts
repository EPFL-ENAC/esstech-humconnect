import type { FeatureCollection, GeoJsonProperties, Geometry, Polygon } from 'geojson';
import type { UserProfileCoordinates } from 'src/utils/model';

const earthRadiusKm = 6371;
const defaultCircleSteps = 96;

export type LngLat = [number, number];
export type LngLatBounds = [LngLat, LngLat];

export function coordinatesToLngLat(coordinates: UserProfileCoordinates): LngLat {
    return [coordinates.longitude, coordinates.latitude];
}

export function emptyFeatureCollection(): FeatureCollection {
    return {
        type: 'FeatureCollection',
        features: [],
    };
}

export function createRadiusCirclePoints(
    coordinates: UserProfileCoordinates,
    radiusKm: number,
    steps = defaultCircleSteps,
): LngLat[] {
    const centerLatitude = (coordinates.latitude * Math.PI) / 180;
    const centerLongitude = (coordinates.longitude * Math.PI) / 180;
    const angularDistance = radiusKm / earthRadiusKm;
    const points: LngLat[] = [];

    for (let step = 0; step <= steps; step += 1) {
        const bearing = (2 * Math.PI * step) / steps;
        const latitude = Math.asin(
            Math.sin(centerLatitude) * Math.cos(angularDistance) +
                Math.cos(centerLatitude) * Math.sin(angularDistance) * Math.cos(bearing),
        );
        const longitude =
            centerLongitude +
            Math.atan2(
                Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(centerLatitude),
                Math.cos(angularDistance) - Math.sin(centerLatitude) * Math.sin(latitude),
            );

        points.push([(longitude * 180) / Math.PI, (latitude * 180) / Math.PI]);
    }

    return points;
}

export function createRadiusCircle(
    coordinates: UserProfileCoordinates,
    radiusKm: number,
): FeatureCollection<Polygon> {
    return {
        type: 'FeatureCollection',
        features: [
            {
                type: 'Feature',
                properties: {},
                geometry: {
                    type: 'Polygon',
                    coordinates: [createRadiusCirclePoints(coordinates, radiusKm)],
                },
            },
        ],
    };
}

export function createRadiusBounds(
    coordinates: UserProfileCoordinates,
    radiusKm: number,
): LngLatBounds {
    return createRadiusCirclePoints(coordinates, radiusKm).reduce<LngLatBounds>(
        (bounds, point) => [
            [Math.min(bounds[0][0], point[0]), Math.min(bounds[0][1], point[1])],
            [Math.max(bounds[1][0], point[0]), Math.max(bounds[1][1], point[1])],
        ],
        [coordinatesToLngLat(coordinates), coordinatesToLngLat(coordinates)],
    );
}

export function calculateRegionBounds(
    regions: FeatureCollection<Geometry, GeoJsonProperties>,
): LngLatBounds | null {
    let minimumLongitude = Number.POSITIVE_INFINITY;
    let minimumLatitude = Number.POSITIVE_INFINITY;
    let maximumLongitude = Number.NEGATIVE_INFINITY;
    let maximumLatitude = Number.NEGATIVE_INFINITY;

    function includePosition(position: LngLat): void {
        minimumLongitude = Math.min(minimumLongitude, position[0]);
        minimumLatitude = Math.min(minimumLatitude, position[1]);
        maximumLongitude = Math.max(maximumLongitude, position[0]);
        maximumLatitude = Math.max(maximumLatitude, position[1]);
    }

    function includeCoordinates(coordinates: unknown): void {
        if (!Array.isArray(coordinates)) {
            return;
        }
        if (
            coordinates.length >= 2 &&
            typeof coordinates[0] === 'number' &&
            typeof coordinates[1] === 'number'
        ) {
            includePosition([coordinates[0], coordinates[1]]);
            return;
        }
        coordinates.forEach(includeCoordinates);
    }

    function includeGeometry(geometry: Geometry): void {
        if (geometry.type === 'GeometryCollection') {
            geometry.geometries.forEach(includeGeometry);
        } else {
            includeCoordinates(geometry.coordinates);
        }
    }

    regions.features.forEach((feature) => includeGeometry(feature.geometry));
    if (
        !Number.isFinite(minimumLongitude) ||
        !Number.isFinite(minimumLatitude) ||
        !Number.isFinite(maximumLongitude) ||
        !Number.isFinite(maximumLatitude)
    ) {
        return null;
    }
    return [
        [minimumLongitude, minimumLatitude],
        [maximumLongitude, maximumLatitude],
    ];
}
