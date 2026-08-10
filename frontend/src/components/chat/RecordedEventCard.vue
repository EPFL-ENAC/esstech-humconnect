<template>
    <ToolCardItem
        color="#444ce7"
        :eyebrow="t('chat.activities.events.recordedEvent')"
        :title="event.event_name"
        :extra-info="extraInfo"
    >
        <template #content>
            <blockquote class="event-quote">{{ event.original_text }}</blockquote>

            <div v-if="event.tags.length" class="event-tags">
                <q-chip v-for="tag in event.tags" :key="tag" dense outline>
                    {{ eventTagLabel(tag) }}
                </q-chip>
            </div>

            <div class="event-severity">
                <div class="severity-local">
                    <span>{{ t('dashboard.severity.local') }}</span>
                    <strong>{{ formatSeverity(event.local_severity) }}</strong>
                </div>
                <div class="severity-country">
                    <span>{{ t('dashboard.severity.country') }}</span>
                    <strong>{{ formatSeverity(event.country_severity) }}</strong>
                </div>
                <div class="severity-global">
                    <span>{{ t('dashboard.severity.global') }}</span>
                    <strong>{{ formatSeverity(event.global_severity) }}</strong>
                </div>
            </div>
        </template>
    </ToolCardItem>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import type { EventTag, RecordedEvent } from 'src/utils/model';
import ToolCardItem from './ToolCardItem.vue';

const props = defineProps<{
    event: RecordedEvent;
}>();

const { t } = useI18n();
const { formatDate, formatNumber } = useLocalizedFormatters();
const extraInfo = computed(() => [
    { icon: 'calendar_today', value: formatEventDateRange() },
    { icon: 'location_on', value: formatLocation() },
]);

function eventTagLabel(tag: EventTag): string {
    return t(`dashboard.tags.${tag}`);
}

function formatEventDateRange(): string {
    const unknownDate = t('chat.activities.events.unknownDate');
    const start = formatDate(props.event.event_datetime, unknownDate);
    if (!props.event.event_end_datetime) {
        return start;
    }

    return `${start} – ${formatDate(props.event.event_end_datetime, unknownDate)}`;
}

function formatLocation(): string {
    const location = props.event.event_location;
    if (location.raw_text) {
        return location.raw_text;
    }

    const parts = [
        location.address,
        location.place_name,
        location.city,
        location.region,
        location.country_code,
        formatContinent(location.continent),
    ].filter((part): part is string => Boolean(part));

    if (!parts.length) {
        return t('chat.activities.events.unknownLocation');
    }

    return parts.join(', ');
}

function formatContinent(continent: RecordedEvent['event_location']['continent']): string | null {
    if (!continent) {
        return null;
    }

    return t(`dashboard.continents.${continent}`);
}

function formatSeverity(value: number | null): string {
    if (value === null) {
        return t('dashboard.severity.notRated');
    }

    const score = formatNumber(value, { maximumFractionDigits: 1 });
    return `${score}/10`;
}
</script>

<style scoped lang="scss">
.event-quote {
    color: #475467;
    display: -webkit-box;
    font-size: 11px;
    font-style: italic;
    line-height: 1.4;
    margin: 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.event-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    margin-top: 9px;
}

.event-tags :deep(.q-chip) {
    color: #475467;
    font-size: 9px;
    margin: 0;
}

.event-tags :deep(.q-chip__content) {
    white-space: normal;
}

.event-severity {
    display: grid;
    gap: 4px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-top: 10px;
}

.event-severity > div {
    border-radius: 5px;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 4px 5px;
}

.event-severity span {
    font-size: 8px;
    font-weight: 650;
    overflow: hidden;
    text-overflow: ellipsis;
    text-transform: uppercase;
    white-space: nowrap;
}

.event-severity strong {
    font-size: 10px;
    font-weight: 700;
}

.severity-local {
    background: #fee4e2;
    color: #b42318;
}

.severity-country {
    background: #fef0c7;
    color: #b54708;
}

.severity-global {
    background: #f4ebff;
    color: #6941c6;
}
</style>
