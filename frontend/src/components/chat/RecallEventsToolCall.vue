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
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                accent-color="#444ce7"
                :query="visualizationQuery"
                :filters="visualizationFilters"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #results>
                    <ChatCardGallery v-if="events?.length">
                        <RecordedEventCard v-for="event in events" :key="event.id" :event="event" />
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
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import RecordedEventCard from './RecordedEventCard.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { RecallEventsToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: RecallEventsToolCallPayload;
}>();

const { locale, t } = useI18n();
const events = computed(() =>
    props.payload.status === 'finished' ? (props.payload.answer?.events ?? null) : null,
);
const tags = computed(() => props.payload.arguments.tags);
const tagsLabel = computed(() => tags.value.map((tag) => t(`dashboard.tags.${tag}`)).join(', '));
const mode = computed(resolveMode);
const summary = computed(resolveSummary);
const visualizationQuery = computed(() =>
    props.payload.arguments.keyword
        ? {
              label: t('chat.activities.events.keyword'),
              value: props.payload.arguments.keyword,
              icon: 'search',
          }
        : null,
);
const visualizationFilters = computed(() => {
    const filters: Array<{ icon: string; label: string; value: string }> = [];
    if (props.payload.arguments.date_start) {
        filters.push({
            icon: 'date_range',
            label: t('chat.activities.events.dateStart'),
            value: formatFilterDate(props.payload.arguments.date_start),
        });
    }
    if (props.payload.arguments.date_end) {
        filters.push({
            icon: 'event',
            label: t('chat.activities.events.dateEnd'),
            value: formatFilterDate(props.payload.arguments.date_end),
        });
    }
    if (tags.value.length) {
        filters.push(
            {
                icon: 'sell',
                label: t('chat.activities.events.tags'),
                value: tagsLabel.value,
            },
            {
                icon: 'rule',
                label: t('chat.activities.events.tagMatch'),
                value: t(`chat.activities.events.tagMatches.${props.payload.arguments.tag_match}`),
            },
        );
    }
    filters.push({
        icon: 'filter_list',
        label: t('chat.activities.events.limit'),
        value: String(props.payload.arguments.limit),
    });
    return filters;
});
const visualizationResultsSummary = computed(() =>
    events.value ? String(events.value.length) : undefined,
);
const visualizationEmptyState = computed(() =>
    events.value && !events.value.length
        ? {
              icon: 'event_busy',
              message: t('chat.activities.events.noResults'),
          }
        : null,
);

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
