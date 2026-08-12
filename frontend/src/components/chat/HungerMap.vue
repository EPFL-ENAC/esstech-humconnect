<template>
    <div class="hunger-map">
        <section
            v-if="response.headline"
            class="headline"
            :aria-label="t('chat.activities.hungerMap.headline')"
        >
            <div class="headline-stat">
                <strong>{{
                    formatMillions(response.headline.acute_food_insecurity_millions)
                }}</strong>
                <span>{{ t('chat.activities.hungerMap.peopleFacingAcuteInsecurity') }}</span>
            </div>
            <div class="headline-stat">
                <strong>{{ formatNumber(response.headline.covered_country_count) }}</strong>
                <span>{{ t('chat.activities.hungerMap.coveredCountries') }}</span>
            </div>
            <div class="headline-context">
                <strong>{{ response.headline.period }}</strong>
                <span>{{ response.headline.source_note }}</span>
            </div>
        </section>

        <template v-if="response.countries.length">
            <div class="map-frame">
                <RegionMap
                    v-if="visibleRegions.features.length"
                    class="hunger-region-map"
                    :regions="visibleRegions"
                    region-code-property="hunger_map_code"
                    :data-by-region="dataByRegion"
                    displayed-property="phase_3_percentage"
                    :color-scale="hungerColorScale"
                    color-interpolation="step"
                    :maximum-value="100"
                    :no-data-color="noDataColor"
                    :ariaLabel="mapAriaLabel"
                    :bounds="mapBounds"
                    :max-zoom="response.scope === 'global' ? 6 : 8"
                    :create-popup-content="createEstimatePopup"
                    :attribution="mapAttribution"
                    @ready="handleMapReady"
                    @render-error="handleMapRenderError"
                />
                <div v-if="renderError" class="map-state map-error-state">
                    <q-icon name="error_outline" size="24px" />
                    <span>{{ t('chat.activities.hungerMap.mapError') }}</span>
                </div>
                <div v-else-if="!visibleRegions.features.length" class="map-state">
                    <q-icon name="map" size="24px" />
                    <span>{{ t('chat.activities.hungerMap.boundariesUnavailable') }}</span>
                </div>
                <div v-else-if="!mapIsReady" class="map-state">
                    <q-spinner color="primary" size="28px" />
                    <span>{{ t('chat.activities.hungerMap.loadingMap') }}</span>
                </div>
            </div>

            <section class="legend" :aria-label="t('chat.activities.hungerMap.legendTitle')">
                <h4>{{ t('chat.activities.hungerMap.legendTitle') }}</h4>
                <div class="legend-items">
                    <div v-for="band in legendBands" :key="band.label" class="legend-item">
                        <span class="legend-swatch" :style="{ backgroundColor: band.color }" />
                        <span>{{ band.label }}</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-swatch" :style="{ backgroundColor: noDataColor }" />
                        <span>{{ t('chat.activities.hungerMap.noData') }}</span>
                    </div>
                </div>
            </section>

            <p class="analysis-scope-note">
                <q-icon name="info_outline" size="16px" />
                <span>{{ t('chat.activities.hungerMap.analysisScopeNote') }}</span>
            </p>
        </template>

        <div v-else class="empty-map">
            <q-icon name="public_off" size="22px" />
            <span>{{ t('chat.activities.hungerMap.noEstimates') }}</span>
        </div>

        <q-banner v-if="unmappedCodes.length" dense rounded class="unmapped-warning">
            <template #avatar><q-icon name="warning_amber" /></template>
            {{
                t('chat.activities.hungerMap.unmappedRegions', {
                    codes: unmappedCodes.join(', '),
                })
            }}
        </q-banner>

        <a
            class="source-link"
            :href="response.source_url"
            target="_blank"
            rel="noopener noreferrer"
        >
            {{ t('chat.activities.hungerMap.openSource') }}
            <q-icon name="open_in_new" size="14px" />
        </a>
    </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { FeatureCollection, Geometry } from 'geojson';
import countryBoundariesJson from 'src/assets/country-boundaries.json';
import RegionMap from 'src/components/maps/RegionMap.vue';
import type { CreatePopupContent, DataByRegion } from 'src/components/maps/regionMap';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import { ColorScale } from 'src/utils/colorScale';
import type { LngLatBounds } from 'src/utils/mapGeometry';
import type { HungerMapCountryEstimate, HungerMapResponse } from './toolCallSchemas';

interface CountryBoundaryProperties {
    name: string;
    country_code: string;
}

interface HungerMapBoundaryProperties extends CountryBoundaryProperties {
    hunger_map_code: string;
}

interface LegendBand {
    color: string;
    label: string;
}

const props = defineProps<{
    response: HungerMapResponse;
}>();

const percentageProperty = 'phase_3_percentage';
const populationProperty = 'phase_3_population';
const noDataColor = '#a6a6a6';
const worldBounds: LngLatBounds = [
    [-180, -85],
    [180, 85],
];
const mapAttribution =
    'Data: <a href="https://hungermap.wfp.org/food?w=ipc-phase-3&amp;m=percentage" target="_blank" rel="noopener noreferrer">WFP HungerMap LIVE</a> · Boundaries: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Natural Earth</a>';
const hungerColorScale = new ColorScale([
    { progress: 0, color: '#fff3b0' },
    { progress: 0.01, color: '#ffe066' },
    { progress: 0.03, color: '#ffb347' },
    { progress: 0.07, color: '#ff8c42' },
    { progress: 0.15, color: '#ff5e3a' },
    { progress: 0.25, color: '#d7263d' },
    { progress: 0.4, color: '#8b0000' },
]);
const countryBoundaries = countryBoundariesJson as unknown as FeatureCollection<
    Geometry,
    CountryBoundaryProperties
>;
const { t } = useI18n();
const { formatDate, formatNumber } = useLocalizedFormatters();
const mapIsReady = ref(false);
const renderError = ref(false);

function hungerMapRegionCode(properties: CountryBoundaryProperties): string {
    if (properties.name === 'Gaza') {
        return 'PSG';
    }
    if (properties.name === 'West Bank') {
        return 'PSW';
    }
    return properties.country_code;
}

function estimateRegionCode(estimate: HungerMapCountryEstimate): string {
    return estimate.wfp_area_code === 'PSG' || estimate.wfp_area_code === 'PSW'
        ? estimate.wfp_area_code
        : estimate.country_code;
}

const hungerMapBoundaries: FeatureCollection<Geometry, HungerMapBoundaryProperties> = {
    type: 'FeatureCollection',
    features: countryBoundaries.features.map((feature) => ({
        ...feature,
        properties: {
            ...feature.properties,
            hunger_map_code: hungerMapRegionCode(feature.properties),
        },
    })),
};
const availableRegionCodes = new Set(
    hungerMapBoundaries.features.map((feature) => feature.properties.hunger_map_code),
);
const estimatesByRegion = computed(
    () =>
        new Map(
            props.response.countries.map((estimate) => [estimateRegionCode(estimate), estimate]),
        ),
);
const requestedRegionCodes = computed(
    () => new Set(props.response.countries.map(estimateRegionCode)),
);
const dataByRegion = computed<DataByRegion>(() =>
    Object.fromEntries(
        props.response.countries.map((estimate) => [
            estimateRegionCode(estimate),
            {
                properties: {
                    [percentageProperty]: estimate.phase_3_or_above.percentage,
                    [populationProperty]: estimate.phase_3_or_above.population,
                },
            },
        ]),
    ),
);
const visibleRegions = computed<FeatureCollection<Geometry, HungerMapBoundaryProperties>>(() => {
    if (props.response.scope === 'global') {
        return hungerMapBoundaries;
    }

    return {
        type: 'FeatureCollection',
        features: hungerMapBoundaries.features.filter((feature) =>
            requestedRegionCodes.value.has(feature.properties.hunger_map_code),
        ),
    };
});
const mapBounds = computed(() => (props.response.scope === 'global' ? worldBounds : undefined));
const unmappedCodes = computed(() =>
    [...requestedRegionCodes.value].filter((code) => !availableRegionCodes.has(code)),
);
const mappedEstimateCount = computed(
    () => [...requestedRegionCodes.value].filter((code) => availableRegionCodes.has(code)).length,
);
const mapAriaLabel = computed(() =>
    t('chat.activities.hungerMap.mapAriaLabel', {
        count: mappedEstimateCount.value,
    }),
);
const legendBands = computed<LegendBand[]>(() => {
    const labels = [
        t('chat.activities.hungerMap.bands.underOne'),
        t('chat.activities.hungerMap.bands.oneToThree'),
        t('chat.activities.hungerMap.bands.threeToSeven'),
        t('chat.activities.hungerMap.bands.sevenToFifteen'),
        t('chat.activities.hungerMap.bands.fifteenToTwentyFive'),
        t('chat.activities.hungerMap.bands.twentyFiveToForty'),
        t('chat.activities.hungerMap.bands.fortyOrMore'),
    ];
    return hungerColorScale.stops.map((stop, index) => ({
        color: stop.color,
        label: labels[index] ?? '',
    }));
});

const createEstimatePopup: CreatePopupContent = (region) => {
    const estimate = estimatesByRegion.value.get(region.code);
    if (!estimate) {
        return null;
    }

    const content = document.createElement('div');
    const title = document.createElement('strong');
    const details = document.createElement('dl');
    title.textContent = estimate.name;
    content.className = 'hunger-map-popup';
    details.className = 'hunger-map-popup-details';
    appendPopupDetail(
        details,
        t('chat.activities.hungerMap.phaseThreePercentage'),
        formatPercentage(estimate.phase_3_or_above.percentage),
    );
    appendPopupDetail(
        details,
        t('chat.activities.hungerMap.affectedPopulation'),
        formatNumber(estimate.phase_3_or_above.population),
    );
    appendPopupDetail(
        details,
        t('chat.activities.hungerMap.referencePeriod'),
        estimate.reference_period,
    );
    appendPopupDetail(
        details,
        t('chat.activities.hungerMap.analysisDate'),
        formatDate(estimate.analysis_date, estimate.analysis_date, {
            dateStyle: 'medium',
            timeZone: 'UTC',
        }),
    );
    appendPopupDetail(details, t('chat.activities.hungerMap.dataSource'), estimate.data_source);
    content.append(title, details);
    return content;
};

function appendPopupDetail(details: HTMLDListElement, label: string, value: string): void {
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = label;
    description.textContent = value;
    details.append(term, description);
}

function formatPercentage(value: number): string {
    return t('chat.activities.hungerMap.percentageValue', {
        value: formatNumber(value, { maximumFractionDigits: 1 }),
    });
}

function formatMillions(value: number): string {
    return t('chat.activities.hungerMap.millionValue', {
        value: formatNumber(value, { maximumFractionDigits: 1 }),
    });
}

function handleMapReady(): void {
    mapIsReady.value = true;
    renderError.value = false;
}

function handleMapRenderError(): void {
    renderError.value = true;
}
</script>

<style scoped lang="scss">
.hunger-map {
    display: grid;
    gap: 12px;
    min-width: 0;
}

.analysis-scope-note {
    align-items: flex-start;
    background: #f8fafc;
    border-radius: 4px;
    color: #475467;
    display: flex;
    font-size: 11px;
    gap: 6px;
    margin: 0;
    padding: 8px 10px;
}

.analysis-scope-note .q-icon {
    color: #007dbc;
    flex: 0 0 auto;
}

.headline {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

.headline-stat,
.headline-context {
    background: #f8fafc;
    border: 1px solid #e4e7ec;
    border-radius: 6px;
    display: grid;
    gap: 2px;
    padding: 10px;
}

.headline-stat strong {
    color: #7a271a;
    font-size: 18px;
}

.headline-stat span,
.headline-context span {
    color: #667085;
    font-size: 11px;
}

.headline-context {
    grid-column: 1 / -1;
}

.headline-context strong {
    color: #344054;
    font-size: 12px;
}

.map-frame {
    background: #dbe7ef;
    border: 1px solid #d0d5dd;
    border-radius: 6px;
    min-height: 340px;
    overflow: hidden;
    position: relative;
}

.hunger-region-map {
    height: 340px;
    width: 100%;
}

.map-state,
.empty-map {
    align-items: center;
    background: rgba(255, 255, 255, 0.86);
    color: #667085;
    display: flex;
    flex-direction: column;
    gap: 8px;
    inset: 0;
    justify-content: center;
    padding: 20px;
    position: absolute;
    text-align: center;
}

.empty-map {
    background: #f8fafc;
    border: 1px dashed #d0d5dd;
    border-radius: 6px;
    min-height: 72px;
    position: static;
}

.map-error-state {
    color: #b42318;
}

.legend h4 {
    color: #475467;
    font-size: 12px;
    margin: 0 0 6px;
}

.legend-items {
    display: grid;
    gap: 5px 10px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
}

.legend-item {
    align-items: center;
    color: #667085;
    display: flex;
    font-size: 10px;
    gap: 5px;
    min-width: 0;
}

.legend-swatch {
    border: 1px solid rgba(0, 0, 0, 0.14);
    border-radius: 2px;
    flex: 0 0 auto;
    height: 10px;
    width: 18px;
}

.unmapped-warning {
    background: #fffaeb;
    color: #7a2e0e;
    font-size: 11px;
}

.source-link {
    align-items: center;
    color: #007dbc;
    display: inline-flex;
    font-size: 11px;
    gap: 3px;
    justify-self: start;
    text-decoration: none;
}

.source-link:hover {
    text-decoration: underline;
}

:deep(.hunger-map-popup) {
    display: grid;
    gap: 6px;
    min-width: 30ch;
}

:deep(.hunger-map-popup-details) {
    display: grid;
    font-size: 11px;
    gap: 2px 10px;
    grid-template-columns: 1fr 15ch;
    margin: 0;
}

:deep(.hunger-map-popup-details dt) {
    color: #667085;
}

:deep(.hunger-map-popup-details dd) {
    color: #344054;
    margin: 0;
    text-align: right;
}

:deep(.maplibregl-popup-content) {
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(16, 24, 40, 0.22);
    padding: 10px 12px;
}

@media (max-width: 700px) {
    .map-frame {
        min-height: 280px;
    }

    .hunger-region-map {
        height: 280px;
    }

    .legend-items {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
