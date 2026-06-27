<template>
    <div class="message-bubble">
        <div v-if="isPendingAssistant" class="pending-message">
            <q-spinner-dots size="24px" color="primary" />
        </div>
        <template v-else-if="message.chunks.length > 0">
            <template v-for="chunk in message.chunks" :key="chunk.index">
                <ReasoningTextChunk v-if="chunk.type === 'reasoning_text'" :chunk="chunk" />
                <MessageContentChunk
                    v-else-if="chunk.type === 'message_content'"
                    :chunk="chunk"
                    :status="message.status"
                />
            </template>
        </template>
        <MessageContentChunk v-else :chunk="emptyChunk" :status="message.status" />
        <div v-if="message.status !== 'complete'" class="message-status">
            {{ statusLabel }}
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ChatMessage } from 'src/utils/model';
import MessageContentChunk from './MessageContentChunk.vue';
import ReasoningTextChunk from './ReasoningTextChunk.vue';

const props = defineProps<{
    message: ChatMessage;
    statusLabel: string;
}>();

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
</script>

<style scoped lang="scss">
.message-bubble {
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    max-width: min(680px, 86%);
    padding: 10px 12px;
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
