<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="event_available"
        color="#039855"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <div v-if="payload.status === 'running'" class="event-loading">
                <q-spinner-dots size="22px" />
            </div>
            <div v-else-if="event" class="recorded-event-single">
                <RecordedEventCard :event="event" />
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
import type { RecordedEvent, ToolCallPayload } from 'src/utils/model';
import ChatActivityBlock from './ChatActivityBlock.vue';
import RecordedEventCard from './RecordedEventCard.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';

interface RecordEventToolResult {
    message: string;
    event: RecordedEvent;
}

type RecordEventToolCallPayload = ToolCallPayload & {
    tool_name: 'record_event';
};

const props = defineProps<{
    payload: RecordEventToolCallPayload;
}>();

const { t } = useI18n();
const result = computed(parseResult);
const event = computed(() => result.value?.event ?? null);
const mode = computed(resolveMode);
const summary = computed(resolveSummary);

function parseResult(): RecordEventToolResult | null {
    if (props.payload.status !== 'finished' || !props.payload.answer) {
        return null;
    }

    try {
        return JSON.parse(props.payload.answer) as RecordEventToolResult;
    } catch {
        return null;
    }
}

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

function truncateUnicode(value: string, maxLength: number): string {
    const characters = Array.from(value);
    if (characters.length <= maxLength) {
        return value;
    }

    return `${characters.slice(0, maxLength - 1).join('')}…`;
}
</script>

<style scoped lang="scss">
.event-loading {
    align-items: center;
    color: #667085;
    display: flex;
    min-height: 48px;
}

.recorded-event-single {
    max-width: 340px;
    width: 100%;
}
</style>
