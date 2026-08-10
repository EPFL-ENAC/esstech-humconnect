<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="event_available"
        :color="toolColor"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                :accent-color="toolColor"
                :query="visualizationQuery"
                :results-summary="event ? '1' : undefined"
            >
                <template #results>
                    <ChatCardGallery v-if="event">
                        <RecordedEventCard :event="event" />
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
import { truncateUnicode } from 'src/utils/text';
import type { RecordEventToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: RecordEventToolCallPayload;
}>();

const toolColor = '#039855';
const { t } = useI18n();
const event = computed(() =>
    props.payload.status === 'finished' ? (props.payload.answer?.event ?? null) : null,
);
const mode = computed(resolveMode);
const summary = computed(resolveSummary);
const visualizationQuery = computed(() => ({
    label: t('chat.activities.events.sourceText'),
    value: props.payload.arguments.original_text,
    icon: 'notes',
}));

function resolveMode(): 'visual-and-raw' | 'raw-only' {
    if (props.payload.status === 'running' || event.value) {
        return 'visual-and-raw';
    }

    return 'raw-only';
}

function resolveSummary(): string {
    if (props.payload.status === 'running') {
        return t('chat.activities.events.recording');
    }

    if (!event.value) {
        return t(`chat.activities.status.${props.payload.status}`);
    }

    return t('chat.activities.events.recorded', {
        name: truncateUnicode(event.value.event_name, 48),
    });
}
</script>
