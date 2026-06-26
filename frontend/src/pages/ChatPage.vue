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

            <div class="messages">
                <div v-if="messages.length === 0" class="empty-state">
                    {{ t('chat.emptyState') }}
                </div>

                <div
                    v-for="message in messages"
                    :key="message.id"
                    class="message-row"
                    :class="message.role"
                >
                    <div class="message-bubble">
                        <div class="message-text">
                            {{ message.content || (message.status === 'streaming' ? '...' : '') }}
                        </div>
                        <div v-if="message.status !== 'complete'" class="message-status">
                            {{ t(`chat.status.${message.status}`) }}
                        </div>
                    </div>
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
import { computed, nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useChat } from 'src/composables/useChat';

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const chatId = computed(() => String(route.params.id));

const draft = ref('');
const { chat, connected, error, messages, sendEvent, onMessageDone } = useChat(chatId);

const connectionLabel = computed(() =>
    connected.value ? t('chat.connected') : t('chat.reconnecting'),
);
const canSend = computed(() => connected.value);
const canSubmit = computed(() => canSend.value && draft.value.trim().length > 0);

function sendMessage() {
    const content = draft.value.trim();
    if (!content) {
        return;
    }

    if (sendEvent({ type: 'user_message', content })) {
        draft.value = '';
    }
}

function handleEnter(event: KeyboardEvent) {
    if (event.shiftKey) {
        return;
    }

    event.preventDefault();
    sendMessage();
}

function scrollToBottom() {
    void nextTick(() => {
        const messagesElement = document.querySelector('.messages');
        messagesElement?.scrollTo({
            top: messagesElement.scrollHeight,
            behavior: 'smooth',
        });
    });
}

function goBack() {
    void router.push('/');
}

watch(messages, scrollToBottom, { deep: true });
onMessageDone(scrollToBottom);
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

.message-bubble {
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    max-width: min(680px, 86%);
    padding: 10px 12px;
    white-space: pre-wrap;
    word-break: break-word;
}

.message-row.user .message-bubble {
    background: #1f6feb;
    color: white;
}

.message-status {
    color: #667085;
    font-size: 12px;
    margin-top: 6px;
}

.message-row.user .message-status {
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
