<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="manage_search"
        color="#444CE7"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <div v-if="payload.status === 'running'" class="events-loading">
                <q-spinner-dots size="22px" />
            </div>
            <div v-else-if="events" class="events-result">
                <section class="recall-filters">
                    <h4>{{ t('chat.activities.events.filters') }}</h4>
                    <div class="filter-pills">
                        <q-chip v-if="payload.arguments?.keyword" dense outline>
                            <span>{{ t('chat.activities.events.keyword') }}:</span>
                            {{ payload.arguments.keyword }}
                        </q-chip>
                        <q-chip v-if="payload.arguments?.date_start" dense outline>
                            <span>{{ t('chat.activities.events.dateStart') }}:</span>
                            {{ formatFilterDate(payload.arguments.date_start) }}
                        </q-chip>
                        <q-chip v-if="payload.arguments?.date_end" dense outline>
                            <span>{{ t('chat.activities.events.dateEnd') }}:</span>
                            {{ formatFilterDate(payload.arguments.date_end) }}
                        </q-chip>
                        <q-chip v-if="tags.length" dense outline>
                            <span>{{ t('chat.activities.events.tags') }}:</span>
                            {{ tagsLabel }}
                        </q-chip>
                        <q-chip dense outline>
                            <span>{{ t('chat.activities.events.tagMatch') }}:</span>
                            {{
                                t(
                                    `chat.activities.events.tagMatches.${payload.arguments?.tag_match ?? 'all'}`,
                                )
                            }}
                        </q-chip>
                        <q-chip dense outline>
                            <span>{{ t('chat.activities.events.limit') }}:</span>
                            {{ payload.arguments?.limit ?? 10 }}
                        </q-chip>
                    </div>
                </section>

                <ChatCardGallery v-if="events.length">
                    <RecordedEventCard v-for="event in events" :key="event.id" :event="event" />
                </ChatCardGallery>
                <div v-else class="empty-events">
                    <q-icon name="event_busy" size="22px" />
                    <span>{{ t('chat.activities.events.noResults') }}</span>
                </div>
            </div>
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { EventTag, RecordedEvent, ToolCallPayload } from 'src/utils/model';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import RecordedEventCard from './RecordedEventCard.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';

interface RecallEventsToolArguments extends Record<string, unknown> {
    keyword?: string | null;
    date_start?: string | null;
    date_end?: string | null;
    tags?: EventTag[] | string;
    tag_match?: 'all' | 'any';
    limit?: number;
}

interface RecallEventsToolResult {
    message: string;
    events: RecordedEvent[];
}

type RecallEventsToolCallPayload = Omit<ToolCallPayload, 'tool_name' | 'arguments'> & {
    tool_name: 'recall_events';
    arguments: RecallEventsToolArguments | null;
};

const props = defineProps<{
    payload: RecallEventsToolCallPayload;
}>();

const { locale, t } = useI18n();
const result = computed(parseResult);
const events = computed(() => result.value?.events ?? null);
const tags = computed(() => {
    const value = props.payload.arguments?.tags ?? [];
    if (typeof value === 'string') {
        return JSON.parse(value) as EventTag[];
    }

    return value;
});
const tagsLabel = computed(() => tags.value.map((tag) => t(`dashboard.tags.${tag}`)).join(', '));
const mode = computed(resolveMode);
const summary = computed(resolveSummary);

function parseResult(): RecallEventsToolResult | null {
    if (props.payload.status !== 'finished' || !props.payload.answer) {
        return null;
    }

    try {
        return JSON.parse(props.payload.answer) as RecallEventsToolResult;
    } catch {
        return null;
    }
}

function resolveMode(): 'visual-and-raw' | 'raw-only' {
    if (props.payload.status === 'running' || events.value) {
        return 'visual-and-raw';
    }

    return 'raw-only';
}

function resolveSummary(): string {
    if (props.payload.status === 'running') {
        return t('chat.activities.events.searching');
    }

    if (!events.value) {
        return t(`chat.activities.status.${props.payload.status}`);
    }

    const count = events.value.length;
    if (count === 1) {
        return t('chat.activities.events.result', { count });
    }

    return t('chat.activities.events.results', { count });
}

function formatFilterDate(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(date);
}
</script>

<style scoped lang="scss">
.events-loading {
    align-items: center;
    color: #667085;
    display: flex;
    min-height: 48px;
}

.recall-filters {
    margin-bottom: 12px;
}

.recall-filters h4 {
    color: #344054;
    font-size: 12px;
    font-weight: 650;
    margin: 0 0 6px;
}

.filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.filter-pills :deep(.q-chip) {
    color: #475467;
    font-size: 10px;
    margin: 0;
    max-width: 100%;
}

.filter-pills :deep(.q-chip__content) {
    overflow-wrap: anywhere;
    white-space: normal;
}

.filter-pills span {
    color: #667085;
    font-weight: 650;
    margin-right: 3px;
}

.empty-events {
    align-items: center;
    background: #f8fafc;
    border: 1px dashed #d0d5dd;
    border-radius: 8px;
    color: #667085;
    display: flex;
    gap: 8px;
    justify-content: center;
    min-height: 72px;
    padding: 12px;
}
</style>
