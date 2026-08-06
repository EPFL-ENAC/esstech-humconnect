<template>
    <article class="recorded-event-card">
        <div class="event-heading">
            <q-icon name="event_note" size="17px" />
            <h5>{{ event.event_name }}</h5>
        </div>

        <blockquote>{{ event.original_text }}</blockquote>

        <dl class="event-meta">
            <div>
                <dt><q-icon name="calendar_today" /></dt>
                <dd>{{ formatEventDateRange() }}</dd>
            </div>
            <div>
                <dt><q-icon name="location_on" /></dt>
                <dd>{{ formatLocation() }}</dd>
            </div>
        </dl>

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
    </article>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { EventTag, RecordedEvent } from 'src/utils/model';

const props = defineProps<{
    event: RecordedEvent;
}>();

const { locale, t } = useI18n();

function eventTagLabel(tag: EventTag): string {
    return t(`dashboard.tags.${tag}`);
}

function formatEventDateRange(): string {
    const start = formatDate(props.event.event_datetime);
    if (!props.event.event_end_datetime) {
        return start;
    }

    return `${start} – ${formatDate(props.event.event_end_datetime)}`;
}

function formatDate(value: string | null): string {
    if (!value) {
        return t('chat.activities.events.unknownDate');
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

    const score = new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 }).format(value);
    return `${score}/10`;
}
</script>

<style scoped lang="scss">
.recorded-event-card {
    background: white;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    color: #344054;
    display: flex;
    flex-direction: column;
    min-height: 230px;
    padding: 11px;
}

.event-heading {
    align-items: flex-start;
    color: #444ce7;
    display: flex;
    gap: 6px;
}

.event-heading h5 {
    color: #101828;
    display: -webkit-box;
    font-size: 13px;
    font-weight: 650;
    line-height: 1.35;
    margin: 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
}

.recorded-event-card blockquote {
    color: #475467;
    display: -webkit-box;
    font-size: 11px;
    font-style: italic;
    line-height: 1.4;
    margin: 8px 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.event-meta {
    color: #667085;
    font-size: 11px;
    margin: 0;
}

.event-meta > div {
    align-items: flex-start;
    display: flex;
    gap: 5px;
    margin-top: 5px;
}

.event-meta dt,
.event-meta dd {
    margin: 0;
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
    margin-top: auto;
    padding-top: 10px;
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
