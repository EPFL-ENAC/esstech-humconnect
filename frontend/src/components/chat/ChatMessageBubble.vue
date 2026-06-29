<template>
    <div class="message-bubble">
        <div v-if="isPendingAssistant" class="pending-message">
            <q-spinner-dots size="24px" color="primary" />
        </div>
        <template v-else-if="message.chunks.length > 0">
            <template v-for="chunk in message.chunks" :key="chunk.index">
                <ReasoningTextChunk v-if="chunk.type === 'reasoning_text'" :chunk="chunk" />
                <ToolCallChunk v-else-if="chunk.type === 'tool_call'" :chunk="chunk" />
                <MessageContentChunk
                    v-else-if="chunk.type === 'message_content'"
                    :chunk="chunk"
                    :status="message.status"
                />
            </template>
        </template>
        <MessageContentChunk v-else :chunk="emptyChunk" :status="message.status" />
        <div v-if="canCopy" class="message-actions">
            <q-btn
                flat
                dense
                round
                size="sm"
                :icon="copied ? 'check' : 'content_copy'"
                :color="message.role === 'user' ? 'white' : 'grey-7'"
                :aria-label="t('chat.copyMessage')"
                @click="copyMessage"
            >
                <q-tooltip>{{ t('chat.copyMessage') }}</q-tooltip>
            </q-btn>
        </div>
        <div v-if="message.status !== 'complete'" class="message-status">
            {{ statusLabel }}
        </div>
    </div>
</template>

<script setup lang="ts">
import { copyToClipboard, useQuasar } from 'quasar';
import { computed, onBeforeUnmount, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ChatMessage } from 'src/utils/model';
import MessageContentChunk from './MessageContentChunk.vue';
import ReasoningTextChunk from './ReasoningTextChunk.vue';
import ToolCallChunk from './ToolCallChunk.vue';

const props = defineProps<{
    message: ChatMessage;
    statusLabel: string;
}>();

const $q = useQuasar();
const { t } = useI18n();
const copied = ref(false);
let copiedTimeout: number | undefined;

const isPendingAssistant = computed(
    () =>
        props.message.role === 'assistant' &&
        props.message.status === 'streaming' &&
        props.message.chunks.length === 0,
);

const emptyChunk = computed(() => ({
    index: 0,
    type: 'message_content' as const,
    content: '',
}));

const copyText = computed(() =>
    props.message.chunks
        .filter((chunk) => chunk.type === 'message_content')
        .map((chunk) => chunk.content)
        .join(''),
);

const canCopy = computed(() => copyText.value.trim().length > 0);

async function copyMessage() {
    try {
        await copyToClipboard(copyText.value);
        copied.value = true;
        if (copiedTimeout !== undefined) {
            window.clearTimeout(copiedTimeout);
        }
        copiedTimeout = window.setTimeout(() => {
            copied.value = false;
            copiedTimeout = undefined;
        }, 1600);
        $q.notify({
            type: 'positive',
            message: t('chat.copiedMessage'),
            timeout: 900,
        });
    } catch {
        $q.notify({
            type: 'negative',
            message: t('chat.copyMessageFailed'),
        });
    }
}

onBeforeUnmount(() => {
    if (copiedTimeout !== undefined) {
        window.clearTimeout(copiedTimeout);
    }
});
</script>

<style scoped lang="scss">
.message-bubble {
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    max-width: min(680px, 86%);
    padding: 10px 12px;
    user-select: text;
}

.message-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
    user-select: none;
}

.message-status {
    color: #667085;
    font-size: 12px;
    margin-top: 6px;
}

.pending-message {
    align-items: center;
    display: flex;
    min-height: 24px;
}
</style>
