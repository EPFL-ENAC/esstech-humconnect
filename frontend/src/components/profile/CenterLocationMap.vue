<template>
    <div class="center-location-map">
        <div ref="mapContainer" class="map-canvas" :aria-label="label" />
        <div v-if="!coordinates" class="map-empty-state">
            {{ emptyLabel }}
        </div>
    </div>
</template>

<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css';

import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import maplibregl, { type GeoJSONSource, type Map, type Marker } from 'maplibre-gl';
import type { UserProfileCoordinates } from 'src/utils/model';
import {
    coordinatesToLngLat,
    createRadiusBounds,
    createRadiusCircle,
    emptyFeatureCollection,
} from 'src/utils/mapGeometry';

const props = defineProps<{
    coordinates: UserProfileCoordinates | null;
    emptyLabel: string;
    label: string;
    radiusKm: number | null;
}>();

const mapContainer = ref<HTMLElement | null>(null);
const radiusSourceId = 'profile-radius-source';
const radiusLayerId = 'profile-radius-layer';
let map: Map | null = null;
let marker: Marker | null = null;

function createMarkerElement() {
    const element = document.createElement('div');
    element.className = 'profile-map-marker';
    return element;
}

function fitMapToRadius(coordinates: UserProfileCoordinates, radiusKm: number) {
    if (!map || radiusKm <= 0) {
        return;
    }

    const bounds = createRadiusBounds(coordinates, radiusKm);

    map.fitBounds(bounds, {
        duration: 500,
        maxZoom: 12,
        padding: 48,
    });
}

function syncRadiusCircle() {
    if (!map || !map.getSource(radiusSourceId)) {
        return;
    }

    const radius = Number(props.radiusKm);
    const data =
        props.coordinates && Number.isFinite(radius) && radius > 0
            ? createRadiusCircle(props.coordinates, radius)
            : emptyFeatureCollection();

    (map.getSource(radiusSourceId) as GeoJSONSource).setData(data);

    if (props.coordinates && Number.isFinite(radius) && radius > 0) {
        fitMapToRadius(props.coordinates, radius);
    }
}

function syncMapToCoordinates() {
    if (!map || !props.coordinates) {
        marker?.remove();
        marker = null;
        syncRadiusCircle();
        return;
    }

    const center = coordinatesToLngLat(props.coordinates);
    if (!marker) {
        marker = new maplibregl.Marker({ element: createMarkerElement() })
            .setLngLat(center)
            .addTo(map);
    } else {
        marker.setLngLat(center);
    }

    if (!props.radiusKm || props.radiusKm <= 0) {
        map.easeTo({
            center,
            duration: 500,
            zoom: Math.max(map.getZoom(), 12),
        });
    }
    syncRadiusCircle();
}

function createMap() {
    if (!mapContainer.value) {
        return;
    }

    const center: [number, number] = props.coordinates
        ? coordinatesToLngLat(props.coordinates)
        : [0, 20];
    map = new maplibregl.Map({
        attributionControl: false,
        center,
        container: mapContainer.value,
        style: {
            version: 8,
            sources: {
                osm: {
                    type: 'raster',
                    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                    tileSize: 256,
                    attribution: 'OpenStreetMap',
                },
            },
            layers: [
                {
                    id: 'osm',
                    type: 'raster',
                    source: 'osm',
                },
            ],
        },
        zoom: props.coordinates ? 12 : 1.4,
    });

    map.on('load', () => {
        map?.addSource(radiusSourceId, {
            type: 'geojson',
            data: {
                type: 'FeatureCollection',
                features: [],
            },
        });
        map?.addLayer({
            id: radiusLayerId,
            type: 'fill',
            source: radiusSourceId,
            paint: {
                'fill-color': '#1976d2',
                'fill-opacity': 0.22,
                'fill-outline-color': '#1976d2',
            },
        });
        syncMapToCoordinates();
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(
        new maplibregl.AttributionControl({
            compact: true,
            customAttribution:
                '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
        }),
        'bottom-right',
    );
}

onMounted(async () => {
    await nextTick();
    createMap();
});

onBeforeUnmount(() => {
    marker?.remove();
    marker = null;
    map?.remove();
    map = null;
});

watch(
    () => props.coordinates,
    () => {
        syncMapToCoordinates();
    },
);

watch(
    () => props.radiusKm,
    () => {
        syncRadiusCircle();
    },
);
</script>

<style scoped lang="scss">
.center-location-map {
    background: #eef2f6;
    border: 1px solid rgba(0, 0, 0, 0.15);
    border-radius: 8px;
    min-height: 280px;
    overflow: hidden;
    position: relative;
}

.map-canvas {
    height: 100%;
    min-height: 280px;
    width: 100%;
}

.map-empty-state {
    align-items: center;
    background: rgba(255, 255, 255, 0.82);
    color: #667085;
    display: flex;
    inset: 0;
    justify-content: center;
    padding: 24px;
    pointer-events: none;
    position: absolute;
    text-align: center;
}

:deep(.profile-map-marker) {
    background: #c62828;
    border: 3px solid #ffffff;
    border-radius: 999px;
    box-shadow: 0 8px 18px rgba(16, 24, 40, 0.28);
    height: 22px;
    width: 22px;
}

:deep(.profile-map-marker::after) {
    background: rgba(198, 40, 40, 0.18);
    border-radius: 999px;
    content: '';
    height: 42px;
    left: 50%;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 42px;
}
</style>
