<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="crisis_alert"
        color="#dc6803"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                accent-color="#dc6803"
                :query="visualizationQuery"
                :filters="visualizationFilters"
                :warnings="result?.warnings"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #query-value>
                    <CenterLocationMap
                        v-if="result"
                        class="natural-events-query-map"
                        :coordinates="result.center"
                        :radius-km="result.center.radius_km"
                        :label="naturalEventsMapLabel"
                        :empty-label="t('chat.activities.naturalEvents.mapUnavailable')"
                    />
                </template>
                <template #results>
                    <ChatCardGallery v-if="result?.events.length">
                        <ToolCardItem
                            v-for="event in result.events"
                            :key="`${event.provider}-${event.id}`"
                            :href="event.source_url ?? undefined"
                            color="#dc6803"
                            :eyebrow="formatProvider(event.provider)"
                            :title="event.title"
                            :extra-info="eventExtraInfo(event)"
                        >
                            <template #content>
                                <div class="event-labels">
                                    <q-badge v-if="event.category" outline color="grey-7">
                                        {{ event.category }}
                                    </q-badge>
                                    <q-badge outline color="orange-9">
                                        {{ formatStatus(event.status) }}
                                    </q-badge>
                                </div>
                            </template>
                        </ToolCardItem>
                    </ChatCardGallery>
                </template>
            </ToolCallVisualizationSkeleton>
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import ToolCardItem from './ToolCardItem.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { NaturalEvent, NaturalEventsToolCallPayload } from './toolCallSchemas';

const CenterLocationMap = defineAsyncComponent(
    () => import('src/components/profile/CenterLocationMap.vue'),
);

const props = defineProps<{
    payload: NaturalEventsToolCallPayload;
}>();

const { locale, t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() =>
    result.value
        ? {
              label: t('chat.activities.naturalEvents.searchArea'),
              value: formatCoordinates(result.value.center.latitude, result.value.center.longitude),
              icon: 'location_on',
          }
        : null,
);
const visualizationFilters = computed(() => {
    return [];
});
const naturalEventsMapLabel = computed(() => {
    if (!result.value) {
        return t('chat.activities.naturalEvents.searchArea');
    }

    return t('chat.activities.naturalEvents.mapLabel', {
        coordinates: formatCoordinates(result.value.center.latitude, result.value.center.longitude),
        radius: formatDistance(result.value.center.radius_km),
    });
});
const visualizationResultsSummary = computed(() =>
    result.value
        ? `NASA EONET: ${result.value.summary.counts.nasa_eonet}, USGS: ${result.value.summary.counts.usgs_earthquakes}, Total: ${result.value.events.length}`
        : undefined,
);
const visualizationEmptyState = computed(() =>
    result.value && !result.value.events.length
        ? {
              icon: 'landscape',
              message: t('chat.activities.naturalEvents.noResults'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.naturalEvents.searching', {
            radius: formatDistance(props.payload.arguments.radius_km),
        });
    }

    if (result.value) {
        const count = result.value.events.length;
        return t(
            count === 1
                ? 'chat.activities.naturalEvents.result'
                : 'chat.activities.naturalEvents.results',
            { count },
        );
    }

    return t(`chat.activities.status.${props.payload.status}`);
});

function formatDate(value: string | null): string {
    if (!value) {
        return t('chat.activities.naturalEvents.unknownDate');
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(date);
}

function formatNumber(value: number, maximumFractionDigits = 1): string {
    return new Intl.NumberFormat(locale.value, { maximumFractionDigits }).format(value);
}

function formatDistance(value: number): string {
    return t('chat.activities.naturalEvents.distanceValue', { value: formatNumber(value) });
}

function formatCoordinates(latitude: number, longitude: number): string {
    return `${formatNumber(latitude, 4)}, ${formatNumber(longitude, 4)}`;
}

function formatProvider(provider: NaturalEvent['provider']): string {
    return provider === 'NASA EONET'
        ? t('chat.activities.naturalEvents.nasaEonet')
        : t('chat.activities.naturalEvents.usgs');
}

function formatStatus(status: string): string {
    const statusKey = status.toLowerCase();
    if (['open', 'closed', 'reviewed', 'automatic'].includes(statusKey)) {
        return t(`chat.activities.naturalEvents.statuses.${statusKey}`);
    }

    return status ? `${status.charAt(0).toUpperCase()}${status.slice(1)}` : '—';
}

function eventExtraInfo(event: NaturalEvent) {
    const info = [
        { icon: 'calendar_today', value: formatDate(event.time) },
        { icon: 'near_me', value: formatDistance(event.distance_km) },
    ];
    if (event.magnitude !== null) {
        info.push({
            icon: 'speed',
            value: `${t('chat.activities.naturalEvents.magnitude')} ${formatNumber(event.magnitude)}`,
        });
    }
    info.push({
        icon: 'location_on',
        value: formatCoordinates(event.latitude, event.longitude),
    });
    return info;
}
</script>

<style scoped lang="scss">
.event-labels {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}
</style>
