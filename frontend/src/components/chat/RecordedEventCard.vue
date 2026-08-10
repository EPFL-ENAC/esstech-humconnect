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
                    {{ formatTag(tag) }}
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
import { useRecordedEventFormatters } from 'src/composables/useRecordedEventFormatters';
import type { RecordedEvent } from 'src/utils/model';
import ToolCardItem from './ToolCardItem.vue';

const props = defineProps<{
    event: RecordedEvent;
}>();

const { t } = useI18n();
const { formatDateRange } = useLocalizedFormatters();
const { formatLocation, formatSeverity, formatTag } = useRecordedEventFormatters();
const extraInfo = computed(() => [
    {
        icon: 'calendar_today',
        value: formatDateRange(
            props.event.event_datetime,
            props.event.event_end_datetime,
            t('chat.activities.events.unknownDate'),
        ),
    },
    {
        icon: 'location_on',
        value: formatLocation(
            props.event.event_location,
            t('chat.activities.events.unknownLocation'),
        ),
    },
]);
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
