<template>
    <q-card flat bordered class="country-map-card">
        <q-card-section class="map-heading">
            <div>
                <h2>{{ t('dashboard.map.title') }}</h2>
                <p>{{ t('dashboard.map.subtitle') }}</p>
            </div>
            <div v-if="!dashboardData.mapLoading" class="map-summary">{{ summary }}</div>
        </q-card-section>

        <div class="map-frame">
            <RegionMap
                class="event-country-region-map"
                :regions="countryBoundaries"
                region-code-property="country_code"
                :data-by-region="dataByRegion"
                displayed-property="event_count"
                :color-scale="eventColorScale"
                :ariaLabel="mapAriaLabel"
                :bounds="worldBounds"
                :create-popup-content="createCountryPopup"
                :attribution="naturalEarthAttribution"
                @ready="handleMapReady"
                @render-error="handleMapRenderError"
            />
            <div v-if="dashboardData.mapError || renderError" class="map-state map-error-state">
                {{ dashboardData.mapError || t('dashboard.map.loadError') }}
            </div>
            <div v-else-if="dashboardData.mapLoading || !mapIsReady" class="map-state">
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
                <div class="legend-scale" :style="{ background: eventLegendGradient }" />
                <span>{{ formatNumber(countryStats.maxCount) }}</span>
            </div>
        </q-card-section>
    </q-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { FeatureCollection, Geometry } from 'geojson';
import countryBoundariesJson from 'src/assets/country-boundaries.json';
import RegionMap from 'src/components/maps/RegionMap.vue';
import type { CreatePopupContent, DataByRegion } from 'src/components/maps/regionMap';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import { useDashboardData } from 'src/queries/dashboard';
import { ColorScale } from 'src/utils/colorScale';
import type { LngLatBounds } from 'src/utils/mapGeometry';

interface CountryBoundaryProperties {
    country_code: string;
}

interface CountryStats {
    countryCount: number;
    mappedEventCount: number;
    maxCount: number;
}

const countryBoundaries = countryBoundariesJson as unknown as FeatureCollection<
    Geometry,
    CountryBoundaryProperties
>;

const countryBoundaryCodes = new Set(
    countryBoundaries.features.map((feature) => feature.properties.country_code),
);
const worldBounds: LngLatBounds = [
    [-180, -85],
    [180, 85],
];
const naturalEarthAttribution =
    'Country boundaries: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Natural Earth</a>';
const eventColorScale = new ColorScale([
    { progress: 0, color: '#f2f4f7' },
    { progress: 0.28, color: '#bbdefb' },
    { progress: 1, color: '#0d47a1' },
]);
const eventLegendGradient = eventColorScale.toLinearGradient();
const renderError = ref(false);
const mapIsReady = ref(false);
const { locale, t } = useI18n();
const { formatNumber } = useLocalizedFormatters();
const dashboardData = useDashboardData();

const dataByRegion = computed<DataByRegion>(() =>
    Object.fromEntries(
        Object.entries(dashboardData.mapData).map(([code, properties]) => [
            code,
            { properties: { event_count: properties.event_count } },
        ]),
    ),
);

const countryStats = computed<CountryStats>(() => {
    const values = Object.entries(dashboardData.mapData)
        .filter(([countryCode]) => countryBoundaryCodes.has(countryCode))
        .map(([, countryData]) => countryData.event_count)
        .filter((count) => count > 0);
    return {
        countryCount: values.length,
        mappedEventCount: values.reduce((total, count) => total + count, 0),
        maxCount: values.length > 0 ? Math.max(...values) : 0,
    };
});

const summary = computed(() =>
    t('dashboard.map.summary', {
        countries: countryCountLabel(countryStats.value.countryCount),
        events: eventCountLabel(countryStats.value.mappedEventCount),
    }),
);

const mapAriaLabel = computed(() =>
    t('dashboard.map.ariaLabel', {
        summary: summary.value,
    }),
);

function eventCountLabel(count: number) {
    return t('dashboard.map.eventCount', { count: formatNumber(count) }, count);
}

function countryCountLabel(count: number) {
    return t('dashboard.map.countryCount', { count: formatNumber(count) }, count);
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

const createCountryPopup: CreatePopupContent = (region, data) => {
    const eventCount = data?.properties.event_count ?? region.displayedValue;
    const content = document.createElement('div');
    const name = document.createElement('strong');
    const count = document.createElement('span');
    name.textContent = countryName(region.code);
    count.textContent = eventCountLabel(eventCount);
    content.className = 'country-popup-content';
    content.append(name, count);
    return content;
};

function handleMapReady(): void {
    mapIsReady.value = true;
    renderError.value = false;
}

function handleMapRenderError(): void {
    renderError.value = true;
}
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

.event-country-region-map {
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
    border: 1px solid rgba(0, 0, 0, 0.16);
    border-radius: 999px;
    height: 10px;
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

    .event-country-region-map {
        height: 300px;
    }

    .map-summary {
        text-align: left;
    }

    .map-legend {
        grid-template-columns: auto minmax(80px, 1fr) auto auto;
    }
}
</style>
