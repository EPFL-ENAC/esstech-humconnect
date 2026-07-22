<template>
    <q-card flat bordered class="country-map-card">
        <q-card-section class="map-heading">
            <div>
                <h2>{{ t('dashboard.map.title') }}</h2>
                <p>{{ t('dashboard.map.subtitle') }}</p>
            </div>
            <div v-if="!loading" class="map-summary">{{ summary }}</div>
        </q-card-section>

        <div class="map-frame">
            <div ref="mapContainer" class="map-canvas" role="region" :aria-label="mapAriaLabel" />
            <div v-if="mapError" class="map-state map-error-state">
                {{ t('dashboard.map.loadError') }}
            </div>
            <div v-else-if="loading || !mapIsReady" class="map-state">
                <q-spinner color="primary" size="32px" />
                <span>{{ t('dashboard.map.loading') }}</span>
            </div>
            <div v-else-if="countryStats.mappedEventCount === 0" class="map-state">
                {{ t('dashboard.map.empty') }}
            </div>
        </div>

        <q-card-section class="map-footer">
            <div class="map-legend" :aria-label="t('dashboard.map.legend')">
                <span>{{ t('dashboard.map.legend') }}</span>
                <span>0</span>
                <div class="legend-scale" />
                <span>{{ formatNumber(countryStats.maxCount) }}</span>
            </div>
            <div v-if="countryStats.unplacedEventCount > 0" class="unplaced-events">
                {{ unplacedEventLabel }}
            </div>
        </q-card-section>
    </q-card>
</template>

<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css';

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import maplibregl, {
    GeoJSONSource,
    type ExpressionSpecification,
    type Map as MapLibreMap,
    type MapLayerMouseEvent,
    type Popup,
} from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import countryBoundariesJson from 'src/assets/country-boundaries.json';
import type { RecordedEvent } from 'src/utils/model';
import { createLightMapStyle } from 'src/utils/mapStyle';

interface CountryBoundaryProperties {
    country_code: string;
}

interface CountryMapProperties extends CountryBoundaryProperties {
    event_count: number;
}

interface CountryStats {
    counts: Map<string, number>;
    mappedEventCount: number;
    maxCount: number;
    unplacedEventCount: number;
}

const props = defineProps<{
    events: readonly RecordedEvent[];
    loading: boolean;
}>();

const countryBoundaries = countryBoundariesJson as unknown as FeatureCollection<
    Geometry,
    CountryBoundaryProperties
>;
const boundaryCountryCodes = new Set(
    countryBoundaries.features.map((feature) => feature.properties.country_code),
);

const countrySourceId = 'event-country-source';
const countryFillLayerId = 'event-country-fill';
const countryLineLayerId = 'event-country-line';
const mapContainer = ref<HTMLElement | null>(null);
const mapError = ref(false);
const mapIsReady = ref(false);
const { locale, t } = useI18n();
let map: MapLibreMap | null = null;
let popup: Popup | null = null;

const countryStats = computed<CountryStats>(() => {
    const counts = new Map<string, number>();
    let unplacedEventCount = 0;

    for (const event of props.events) {
        const countryCode = event.event_location.country_code?.trim().toUpperCase();
        if (!countryCode || !boundaryCountryCodes.has(countryCode)) {
            unplacedEventCount += 1;
            continue;
        }
        counts.set(countryCode, (counts.get(countryCode) ?? 0) + 1);
    }

    const values = [...counts.values()];
    return {
        counts,
        mappedEventCount: values.reduce((total, count) => total + count, 0),
        maxCount: values.length > 0 ? Math.max(...values) : 0,
        unplacedEventCount,
    };
});

const summary = computed(() =>
    t('dashboard.map.summary', {
        countries: countryCountLabel(countryStats.value.counts.size),
        events: eventCountLabel(countryStats.value.mappedEventCount),
    }),
);

const mapAriaLabel = computed(() =>
    t('dashboard.map.ariaLabel', {
        summary: summary.value,
    }),
);

const unplacedEventLabel = computed(() => {
    const count = countryStats.value.unplacedEventCount;
    return t(count === 1 ? 'dashboard.map.unplacedEventOne' : 'dashboard.map.unplacedEventOther', {
        count: formatNumber(count),
    });
});

function formatNumber(value: number) {
    return new Intl.NumberFormat(locale.value).format(value);
}

function eventCountLabel(count: number) {
    return t(count === 1 ? 'dashboard.map.eventCountOne' : 'dashboard.map.eventCountOther', {
        count: formatNumber(count),
    });
}

function countryCountLabel(count: number) {
    return t(count === 1 ? 'dashboard.map.countryCountOne' : 'dashboard.map.countryCountOther', {
        count: formatNumber(count),
    });
}

function countryName(countryCode: string) {
    try {
        return (
            new Intl.DisplayNames([locale.value], { type: 'region' }).of(countryCode) ?? countryCode
        );
    } catch {
        return countryCode;
    }
}

function createCountryData(): FeatureCollection<Geometry, CountryMapProperties> {
    return {
        type: 'FeatureCollection',
        features: countryBoundaries.features.map(
            (feature): Feature<Geometry, CountryMapProperties> => ({
                ...feature,
                properties: {
                    country_code: feature.properties.country_code,
                    event_count:
                        countryStats.value.counts.get(feature.properties.country_code) ?? 0,
                },
            }),
        ),
    };
}

function createFillColorExpression(): string | ExpressionSpecification {
    if (countryStats.value.maxCount <= 1) {
        return [
            'case',
            ['>', ['get', 'event_count'], 0],
            '#1976d2',
            '#f2f4f7',
        ] as ExpressionSpecification;
    }
    return [
        'case',
        ['==', ['get', 'event_count'], 0],
        '#f2f4f7',
        [
            'interpolate',
            ['linear'],
            ['get', 'event_count'],
            1,
            '#bbdefb',
            countryStats.value.maxCount,
            '#0d47a1',
        ],
    ] as ExpressionSpecification;
}

function syncCountryData() {
    if (!mapIsReady.value || !map) {
        return;
    }
    const source = map.getSource(countrySourceId);
    if (source instanceof GeoJSONSource) {
        source.setData(createCountryData());
    }
    map.setPaintProperty(countryFillLayerId, 'fill-color', createFillColorExpression());
}

function showCountryPopup(event: MapLayerMouseEvent) {
    const feature = event.features?.[0];
    const rawCountryCode = feature?.properties.country_code;
    const countryCode = typeof rawCountryCode === 'string' ? rawCountryCode : undefined;
    const eventCount = Number(feature?.properties.event_count ?? 0);
    if (!countryCode || !popup || !map) {
        return;
    }

    const content = document.createElement('div');
    const name = document.createElement('strong');
    const count = document.createElement('span');
    name.textContent = countryName(countryCode);
    count.textContent = eventCountLabel(eventCount);
    content.className = 'country-popup-content';
    content.append(name, count);

    popup.setLngLat(event.lngLat).setDOMContent(content).addTo(map);
}

function createMap() {
    if (!mapContainer.value) {
        return;
    }

    try {
        map = new maplibregl.Map({
            attributionControl: false,
            center: [0, 15],
            container: mapContainer.value,
            dragRotate: false,
            maxZoom: 6,
            minZoom: 0,
            pitchWithRotate: false,
            style: createLightMapStyle(),
            zoom: 0.7,
        });
        popup = new maplibregl.Popup({
            closeButton: false,
            closeOnClick: true,
            offset: 10,
        });

        map.on('load', () => {
            if (!map) {
                return;
            }
            try {
                map.addSource(countrySourceId, {
                    type: 'geojson',
                    data: createCountryData(),
                });
                map.addLayer({
                    id: countryFillLayerId,
                    type: 'fill',
                    source: countrySourceId,
                    paint: {
                        'fill-color': createFillColorExpression(),
                        'fill-opacity': 0.72,
                    },
                });
                map.addLayer({
                    id: countryLineLayerId,
                    type: 'line',
                    source: countrySourceId,
                    paint: {
                        'line-color': '#475467',
                        'line-opacity': 0.7,
                        'line-width': 0.55,
                    },
                });
                map.on('mousemove', countryFillLayerId, showCountryPopup);
                map.on('click', countryFillLayerId, showCountryPopup);
                map.on('mouseenter', countryFillLayerId, () => {
                    if (map) {
                        map.getCanvas().style.cursor = 'pointer';
                    }
                });
                map.on('mouseleave', countryFillLayerId, () => {
                    if (map) {
                        map.getCanvas().style.cursor = '';
                    }
                    popup?.remove();
                });
                map.fitBounds(
                    [
                        [-180, -85],
                        [180, 85],
                    ],
                    { duration: 0, padding: 18 },
                );
                mapIsReady.value = true;
            } catch {
                mapError.value = true;
            }
        });

        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
        map.addControl(
            new maplibregl.AttributionControl({
                compact: true,
                customAttribution:
                    'Country boundaries: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Natural Earth</a>',
            }),
            'bottom-right',
        );
    } catch {
        mapError.value = true;
    }
}

onMounted(async () => {
    await nextTick();
    createMap();
});

onBeforeUnmount(() => {
    popup?.remove();
    popup = null;
    map?.remove();
    map = null;
});

watch(countryStats, () => {
    syncCountryData();
});
</script>

<style scoped lang="scss">
.country-map-card {
    margin-bottom: 20px;
}

.map-heading {
    align-items: flex-start;
    display: flex;
    gap: 24px;
    justify-content: space-between;
}

h2 {
    font-size: 18px;
    line-height: 1.3;
    margin: 0 0 4px;
}

p {
    color: #667085;
    margin: 0;
}

.map-summary {
    color: #344054;
    flex: 0 0 auto;
    font-size: 13px;
    font-weight: 600;
    padding-top: 4px;
}

.map-frame {
    background: #dbe7ef;
    border-bottom: 1px solid rgba(0, 0, 0, 0.12);
    border-top: 1px solid rgba(0, 0, 0, 0.12);
    min-height: 420px;
    position: relative;
}

.map-canvas {
    height: 420px;
    width: 100%;
}

.map-state {
    align-items: center;
    background: rgba(255, 255, 255, 0.82);
    color: #667085;
    display: flex;
    flex-direction: column;
    gap: 12px;
    inset: 0;
    justify-content: center;
    padding: 24px;
    pointer-events: none;
    position: absolute;
    text-align: center;
}

.map-error-state {
    color: #b42318;
}

.map-footer {
    align-items: center;
    display: flex;
    gap: 24px;
    justify-content: space-between;
    min-height: 50px;
    padding-bottom: 10px;
    padding-top: 10px;
}

.map-legend {
    align-items: center;
    color: #475467;
    display: grid;
    font-size: 12px;
    gap: 4px 8px;
    grid-template-columns: auto auto minmax(120px, 180px) auto;
}

.legend-scale {
    background: linear-gradient(90deg, #f2f4f7 0%, #bbdefb 28%, #0d47a1 100%);
    border: 1px solid rgba(0, 0, 0, 0.16);
    border-radius: 999px;
    height: 10px;
}

.unplaced-events {
    color: #667085;
    font-size: 12px;
    text-align: right;
}

:deep(.country-popup-content) {
    display: grid;
    gap: 2px;
}

:deep(.country-popup-content span) {
    color: #667085;
    font-size: 12px;
}

:deep(.maplibregl-popup-content) {
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(16, 24, 40, 0.22);
    padding: 9px 11px;
}

@media (max-width: 760px) {
    .map-heading,
    .map-footer {
        align-items: stretch;
        flex-direction: column;
        gap: 10px;
    }

    .map-frame {
        min-height: 300px;
    }

    .map-canvas {
        height: 300px;
    }

    .map-summary,
    .unplaced-events {
        text-align: left;
    }

    .map-legend {
        grid-template-columns: auto minmax(80px, 1fr) auto auto;
    }
}
</style>
