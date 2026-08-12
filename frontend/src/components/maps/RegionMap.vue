<template>
    <div ref="mapContainer" class="region-map" role="region" :aria-label="ariaLabel" />
</template>

<script setup lang="ts">
import 'maplibre-gl/dist/maplibre-gl.css';

import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import maplibregl, {
    GeoJSONSource,
    type Map as MapLibreMap,
    type MapLayerMouseEvent,
    type Popup,
} from 'maplibre-gl';
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import type { ColorScale } from 'src/utils/colorScale';
import { type LngLatBounds, calculateRegionBounds } from 'src/utils/mapGeometry';
import { createLightMapStyle } from 'src/utils/mapStyle';
import type { CreatePopupContent, DataByRegion } from './regionMap';

const props = withDefaults(
    defineProps<{
        regions: FeatureCollection<Geometry, GeoJsonProperties>;
        regionCodeProperty: string;
        dataByRegion: DataByRegion;
        displayedProperty: string;
        colorScale: ColorScale;
        colorInterpolation?: 'linear' | 'step';
        maximumValue?: number;
        noDataColor?: string;
        ariaLabel: string;
        createPopupContent?: CreatePopupContent;
        bounds?: LngLatBounds | undefined;
        maxZoom?: number;
        attribution?: string;
    }>(),
    {
        colorInterpolation: 'linear',
        maxZoom: 6,
    },
);

const emit = defineEmits<{
    ready: [];
    renderError: [];
}>();

const sourceId = 'region-map-source';
const fillLayerId = 'region-map-fill';
const lineLayerId = 'region-map-line';
const internalCodeProperty = '__humconnect_region_code';
const internalProgressProperty = '__humconnect_region_progress';
const internalFeatureIndexProperty = '__humconnect_region_feature_index';
const mapContainer = ref<HTMLElement | null>(null);
let map: MapLibreMap | null = null;
let popup: Popup | null = null;
let resizeObserver: ResizeObserver | null = null;
let mapIsReady = false;

function regionCode(feature: Feature<Geometry, GeoJsonProperties>): string | null {
    const value = feature.properties?.[props.regionCodeProperty];
    return typeof value === 'string' && value ? value : null;
}

function validDisplayedValue(code: string | null): number | null {
    if (!code) {
        return null;
    }
    const value = props.dataByRegion[code]?.properties[props.displayedProperty];
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function displayedValue(code: string | null): number {
    return validDisplayedValue(code) ?? 0;
}

function maximumMappedValue(): number {
    if (props.maximumValue !== undefined) {
        if (!Number.isFinite(props.maximumValue) || props.maximumValue <= 0) {
            throw new RangeError('RegionMap maximumValue must be a finite positive number.');
        }
        return props.maximumValue;
    }

    return props.regions.features.reduce((maximum, feature) => {
        return Math.max(maximum, displayedValue(regionCode(feature)));
    }, 0);
}

function createRegionData(): FeatureCollection<Geometry, GeoJsonProperties> {
    const maximum = maximumMappedValue();
    return {
        type: 'FeatureCollection',
        features: props.regions.features.map((feature, index) => {
            const code = regionCode(feature);
            const validValue = validDisplayedValue(code);
            const properties: Record<string, unknown> = {
                ...(feature.properties ?? {}),
                [internalCodeProperty]: code ?? '',
                [internalFeatureIndexProperty]: index,
            };
            delete properties[internalProgressProperty];
            if (validValue !== null) {
                properties[internalProgressProperty] =
                    maximum > 0 ? Math.min(validValue / maximum, 1) : 0;
            }

            return {
                ...feature,
                properties,
            };
        }),
    };
}

function createFillColorExpression() {
    return props.colorScale.toMapLibreExpression(
        props.colorInterpolation,
        internalProgressProperty,
        props.noDataColor,
    );
}

function syncRegionData(): void {
    if (!mapIsReady || !map) {
        return;
    }
    try {
        const source = map.getSource(sourceId);
        if (source instanceof GeoJSONSource) {
            source.setData(createRegionData());
        }
        map.setPaintProperty(fillLayerId, 'fill-color', createFillColorExpression());
    } catch {
        emit('renderError');
    }
}

function showRegionPopup(event: MapLayerMouseEvent): void {
    if (!props.createPopupContent || !popup || !map) {
        return;
    }

    const renderedFeature = event.features?.[0];
    const rawCode = renderedFeature?.properties[internalCodeProperty];
    const rawFeatureIndex = renderedFeature?.properties[internalFeatureIndexProperty];
    const code = typeof rawCode === 'string' ? rawCode : null;
    const featureIndex = Number(rawFeatureIndex);
    const feature = Number.isInteger(featureIndex)
        ? props.regions.features[featureIndex]
        : undefined;
    if (!code || !feature) {
        popup.remove();
        return;
    }

    const data = props.dataByRegion[code];
    const content = props.createPopupContent(
        { code, feature, displayedValue: displayedValue(code) },
        data,
    );
    if (!content) {
        popup.remove();
        return;
    }

    popup.setLngLat(event.lngLat).setDOMContent(content).addTo(map).setMaxWidth('50ch');
}

function fitMapToRegions(): void {
    if (!map) {
        return;
    }
    const bounds = props.bounds ?? calculateRegionBounds(props.regions);
    if (!bounds) {
        return;
    }
    map.fitBounds(bounds, {
        duration: 0,
        maxZoom: props.maxZoom,
        padding: 18,
    });
}

function createMap(): void {
    if (!mapContainer.value) {
        return;
    }

    try {
        map = new maplibregl.Map({
            attributionControl: false,
            center: [0, 15],
            container: mapContainer.value,
            dragRotate: false,
            maxZoom: props.maxZoom,
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
                map.addSource(sourceId, {
                    type: 'geojson',
                    data: createRegionData(),
                });
                map.addLayer({
                    id: fillLayerId,
                    type: 'fill',
                    source: sourceId,
                    paint: {
                        'fill-color': createFillColorExpression(),
                        'fill-opacity': 0.72,
                    },
                });
                map.addLayer({
                    id: lineLayerId,
                    type: 'line',
                    source: sourceId,
                    paint: {
                        'line-color': '#475467',
                        'line-opacity': 0.7,
                        'line-width': 0.55,
                    },
                });
                map.on('mousemove', fillLayerId, showRegionPopup);
                map.on('click', fillLayerId, showRegionPopup);
                map.on('mouseenter', fillLayerId, () => {
                    if (map) {
                        map.getCanvas().style.cursor = props.createPopupContent ? 'pointer' : '';
                    }
                });
                map.on('mouseleave', fillLayerId, () => {
                    if (map) {
                        map.getCanvas().style.cursor = '';
                    }
                    popup?.remove();
                });
                fitMapToRegions();
                mapIsReady = true;
                emit('ready');
            } catch {
                emit('renderError');
            }
        });

        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
        map.addControl(
            new maplibregl.AttributionControl({
                compact: true,
                ...(props.attribution ? { customAttribution: props.attribution } : {}),
            }),
            'bottom-right',
        );
        resizeObserver = new ResizeObserver(() => map?.resize());
        resizeObserver.observe(mapContainer.value);
    } catch {
        emit('renderError');
    }
}

onMounted(async () => {
    await nextTick();
    createMap();
});

onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    resizeObserver = null;
    popup?.remove();
    popup = null;
    map?.remove();
    map = null;
    mapIsReady = false;
});

watch(
    () => [
        props.regions,
        props.regionCodeProperty,
        props.dataByRegion,
        props.displayedProperty,
        props.colorScale,
        props.colorInterpolation,
        props.maximumValue,
        props.noDataColor,
    ],
    syncRegionData,
);

watch(
    () => [props.regions, props.bounds, props.maxZoom] as const,
    () => {
        map?.setMaxZoom(props.maxZoom);
        fitMapToRegions();
    },
);
</script>

<style scoped lang="scss">
.region-map {
    height: 100%;
    width: 100%;
}
</style>
