<template>
    <q-expansion-item expand-separator group="recorded-events">
        <template #header>
            <q-item-section>
                <q-item-label class="event-title">{{ event.event_name }}</q-item-label>
                <q-item-label caption>{{ event.original_text }}</q-item-label>
            </q-item-section>
            <q-item-section side class="event-meta">
                <span>{{ eventDateRange }}</span>
            </q-item-section>
        </template>

        <div class="event-details">
            <dl>
                <div>
                    <dt>{{ t('dashboard.fields.createdAt') }}</dt>
                    <dd>{{ formatDate(event.created_at, '-') }}</dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.eventStartDate') }}</dt>
                    <dd>{{ formatDate(event.event_datetime, '-') }}</dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.startDateQuality') }}</dt>
                    <dd>{{ event.event_date_granularity }} / {{ event.event_date_precision }}</dd>
                </div>
                <div v-if="event.event_end_datetime">
                    <dt>{{ t('dashboard.fields.eventEndDate') }}</dt>
                    <dd>{{ formatDate(event.event_end_datetime, '-') }}</dd>
                </div>
                <div v-if="event.event_end_datetime">
                    <dt>{{ t('dashboard.fields.endDateQuality') }}</dt>
                    <dd>
                        {{ event.event_end_date_granularity }} /
                        {{ event.event_end_date_precision }}
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.location') }}</dt>
                    <dd>{{ eventLocation }}</dd>
                </div>
                <div v-if="event.event_location.continent">
                    <dt>{{ t('dashboard.fields.continent') }}</dt>
                    <dd>{{ formatContinent(event.event_location.continent) }}</dd>
                </div>
                <div v-if="event.event_location.country_code">
                    <dt>{{ t('dashboard.fields.countryCode') }}</dt>
                    <dd>{{ event.event_location.country_code }}</dd>
                </div>
                <div v-if="event.event_location.region">
                    <dt>{{ t('dashboard.fields.region') }}</dt>
                    <dd>{{ event.event_location.region }}</dd>
                </div>
                <div v-if="event.event_location.city">
                    <dt>{{ t('dashboard.fields.city') }}</dt>
                    <dd>{{ event.event_location.city }}</dd>
                </div>
                <div v-if="event.event_location.address">
                    <dt>{{ t('dashboard.fields.address') }}</dt>
                    <dd>{{ event.event_location.address }}</dd>
                </div>
                <div v-if="event.event_location.place_name">
                    <dt>{{ t('dashboard.fields.placeName') }}</dt>
                    <dd>{{ event.event_location.place_name }}</dd>
                </div>
                <div v-if="event.event_location.detail">
                    <dt>{{ t('dashboard.fields.locationDetail') }}</dt>
                    <dd>{{ event.event_location.detail }}</dd>
                </div>
                <div v-if="event.event_location.coordinates">
                    <dt>{{ t('dashboard.fields.coordinates') }}</dt>
                    <dd class="monospace">
                        {{ formatCoordinates(event.event_location.coordinates, coordinateOptions) }}
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.severity') }}</dt>
                    <dd>
                        <q-chip dense color="red-2" text-color="red-10">
                            {{ t('dashboard.severity.local') }}:
                            {{ formatSeverity(event.local_severity, severityOptions) }}
                        </q-chip>
                        <q-chip dense color="orange-2" text-color="orange-10">
                            {{ t('dashboard.severity.country') }}:
                            {{ formatSeverity(event.country_severity, severityOptions) }}
                        </q-chip>
                        <q-chip dense color="purple-2" text-color="purple-10">
                            {{ t('dashboard.severity.global') }}:
                            {{ formatSeverity(event.global_severity, severityOptions) }}
                        </q-chip>
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.tags') }}</dt>
                    <dd>
                        <q-chip
                            v-for="tag in event.tags"
                            :key="tag"
                            dense
                            color="primary"
                            text-color="white"
                        >
                            {{ formatTag(tag) }}
                        </q-chip>
                        <span v-if="event.tags.length === 0">-</span>
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.keywords') }}</dt>
                    <dd>
                        <q-chip
                            v-for="keyword in event.keywords"
                            :key="keyword"
                            dense
                            color="grey-4"
                            text-color="grey-9"
                        >
                            {{ keyword }}
                        </q-chip>
                        <span v-if="event.keywords.length === 0">-</span>
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.affectedProfessions') }}</dt>
                    <dd>
                        <q-chip
                            v-for="category in event.affected_profession_categories"
                            :key="category"
                            dense
                            color="orange-2"
                            text-color="orange-10"
                        >
                            {{ t(`profile.categories.${category}`) }}
                        </q-chip>
                        <span v-if="event.affected_profession_categories.length === 0">-</span>
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.responseProfessions') }}</dt>
                    <dd>
                        <q-chip
                            v-for="category in event.response_profession_categories"
                            :key="category"
                            dense
                            color="green-2"
                            text-color="green-10"
                        >
                            {{ t(`profile.categories.${category}`) }}
                        </q-chip>
                        <span v-if="event.response_profession_categories.length === 0">-</span>
                    </dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.chatId') }}</dt>
                    <dd class="monospace">{{ event.chat_id }}</dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.userId') }}</dt>
                    <dd class="monospace">{{ event.initiated_by_user_id }}</dd>
                </div>
                <div>
                    <dt>{{ t('dashboard.fields.sourceMessageId') }}</dt>
                    <dd class="monospace">{{ event.source_message_id }}</dd>
                </div>
            </dl>

            <div class="json-grid">
                <div>
                    <h2>{{ t('dashboard.fields.startDateInput') }}</h2>
                    <pre>{{ prettyPrintJson(event.event_date_input) }}</pre>
                </div>
                <div v-if="event.event_end_date_input">
                    <h2>{{ t('dashboard.fields.endDateInput') }}</h2>
                    <pre>{{ prettyPrintJson(event.event_end_date_input) }}</pre>
                </div>
            </div>
        </div>
    </q-expansion-item>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import { useRecordedEventFormatters } from 'src/composables/useRecordedEventFormatters';
import type { RecordedEvent } from 'src/utils/model';
import { prettyPrintJson } from 'src/utils/text';

const props = defineProps<{
    event: RecordedEvent;
}>();

const coordinateOptions: Intl.NumberFormatOptions = {
    maximumFractionDigits: 5,
    minimumFractionDigits: 5,
};
const severityOptions: Intl.NumberFormatOptions = { maximumFractionDigits: 2 };
const { t } = useI18n();
const { formatCoordinates, formatDate, formatDateRange } = useLocalizedFormatters();
const { formatContinent, formatLocation, formatSeverity, formatTag } = useRecordedEventFormatters();
const eventDateRange = computed(() =>
    formatDateRange(
        props.event.event_datetime ?? props.event.created_at,
        props.event.event_end_datetime,
        '-',
    ),
);
const eventLocation = computed(() => formatLocation(props.event.event_location, '-'));
</script>

<style scoped lang="scss">
.event-title {
    font-weight: 600;
}

.event-meta {
    color: #667085;
    font-size: 13px;
    min-width: 180px;
    text-align: right;
}

.event-details {
    background: #f7f8fa;
    padding: 18px 24px 24px;
}

dl {
    display: grid;
    gap: 14px 24px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 0 0 20px;
}

dt {
    color: #667085;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
    margin-bottom: 4px;
    text-transform: uppercase;
}

dd {
    margin: 0;
    overflow-wrap: anywhere;
}

.monospace,
pre {
    font-family: 'Roboto Mono', monospace;
}

.json-grid {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

h2 {
    font-size: 14px;
    margin: 0 0 8px;
}

pre {
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.45;
    margin: 0;
    max-height: 260px;
    overflow: auto;
    padding: 12px;
    user-select: text;
}

@media (max-width: 760px) {
    .event-meta {
        display: none;
    }

    dl,
    .json-grid {
        grid-template-columns: 1fr;
    }
}
</style>
