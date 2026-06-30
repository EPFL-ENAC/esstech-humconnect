<template>
    <q-page class="chat-page">
        <section class="chat-shell">
            <div class="chat-header">
                <q-btn flat round icon="arrow_back" @click="goBack">
                    <q-tooltip>{{ t('chat.backToChats') }}</q-tooltip>
                </q-btn>
                <div>
                    <h1>{{ chat?.title || t('chat.newChat') }}</h1>
                    <p>{{ connectionLabel }}</p>
                </div>
            </div>

            <q-banner v-if="error" class="bg-red-1 text-red-9" rounded>
                {{ error }}
            </q-banner>

            <div ref="messagesElement" class="messages">
                <div v-if="messages.length === 0" class="empty-state">
                    {{ t('chat.emptyState') }}
                </div>

                <div
                    v-for="message in messages"
                    :key="message.id"
                    class="message-row"
                    :class="message.role"
                >
                    <ChatMessageBubble
                        :message="message"
                        :status-label="t(`chat.status.${message.status}`)"
                    />
                </div>
            </div>

            <form class="composer" @submit.prevent="sendMessage">
                <q-input
                    v-model="draft"
                    outlined
                    dense
                    autogrow
                    :placeholder="t('chat.writeMessage')"
                    :disable="!canSend"
                    @keydown.enter="handleEnter"
                />
                <q-btn round color="primary" icon="send" type="submit" :disable="!canSubmit">
                    <q-tooltip>{{ t('chat.send') }}</q-tooltip>
                </q-btn>
            </form>
        </section>
    </q-page>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useChat } from 'src/composables/useChat';
import ChatMessageBubble from 'src/components/chat/ChatMessageBubble.vue';

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const chatId = computed(() => String(route.params.id));

const draft = ref('');
const messagesElement = ref<HTMLElement | null>(null);
const {
    chat,
    connected,
    error,
    messages,
    sendMessage: submitMessage,
    onMessageDone,
} = useChat(chatId);
let scrollFrame: number | undefined;

const connectionLabel = computed(() =>
    connected.value ? t('chat.connected') : t('chat.reconnecting'),
);
const canSend = computed(() => connected.value);
const canSubmit = computed(() => canSend.value && draft.value.trim().length > 0);

async function sendMessage() {
    const content = draft.value.trim();
    if (!content) {
        return;
    }

    if (await submitMessage(content)) {
        draft.value = '';
    }
}

function handleEnter(event: KeyboardEvent) {
    if (event.shiftKey) {
        return;
    }

    event.preventDefault();
    void sendMessage();
}

function scheduleScrollToBottom() {
    if (scrollFrame !== undefined) {
        return;
    }

    scrollFrame = window.requestAnimationFrame(() => {
        scrollFrame = undefined;
        const element = messagesElement.value;
        element?.scrollTo({
            top: element.scrollHeight,
            behavior: 'smooth',
        });
    });
}

function goBack() {
    void router.push('/');
}

watch(messages, scheduleScrollToBottom, { deep: true, flush: 'post' });
onMessageDone(scheduleScrollToBottom);

onBeforeUnmount(() => {
    if (scrollFrame !== undefined) {
        window.cancelAnimationFrame(scrollFrame);
    }
});
</script>

<style scoped lang="scss">
.chat-page {
    padding: 24px;
}

.chat-shell {
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: calc(100vh - 98px);
    max-width: 920px;
}

.chat-header {
    align-items: center;
    display: flex;
    gap: 12px;
}

h1 {
    font-size: 24px;
    line-height: 1.2;
    margin: 0;
}

p {
    color: #667085;
    margin: 2px 0 0;
}

.messages {
    background: #f7f8fa;
    border: 1px solid rgba(0, 0, 0, 0.12);
    flex: 1;
    min-height: 260px;
    overflow-y: auto;
    padding: 18px;
}

.empty-state {
    color: #667085;
    padding: 24px;
    text-align: center;
}

.message-row {
    display: flex;
    margin-bottom: 12px;
}

.message-row.user {
    justify-content: flex-end;
}

.message-row.assistant {
    justify-content: flex-start;
}

.message-row.user :deep(.message-bubble) {
    background: #1f6feb;
    color: white;
}

.message-row.user :deep(.message-status) {
    color: rgba(255, 255, 255, 0.82);
}

.composer {
    align-items: flex-end;
    display: grid;
    gap: 10px;
    grid-template-columns: minmax(0, 1fr) auto;
}

@media (max-width: 640px) {
    .chat-page {
        padding: 16px;
    }

    .chat-shell {
        height: calc(100vh - 82px);
    }
}
</style>
