import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue';
import { useApiEventStream } from 'src/composables/useApiEventStream';
import { chatEventStreamUrl, createChatMessage } from 'src/utils/chatApi';
import type { ChatMessage, ChatSession, ChatStreamEvent } from 'src/utils/model';
import { getI18nT } from 'src/utils/i18n';
import { useChatsStore } from 'src/stores/chats';

type ChatId = string | number;
type MessageDoneCallback = (message: ChatMessage | undefined) => void;

export function useChat(chatId: MaybeRefOrGetter<ChatId>) {
    const t = getI18nT();
    const chatsStore = useChatsStore();
    const chat = ref<ChatSession | null>(null);
    const error = ref('');
    const messages = ref<ChatMessage[]>([]);

    const messageDoneCallbacks = new Set<MessageDoneCallback>();

    const streamUrl = computed(() => chatEventStreamUrl(String(toValue(chatId))));
    const { connected, error: streamError } = useApiEventStream<ChatStreamEvent>({
        url: streamUrl,
        onEvent: handleChatEvent,
    });

    watch(streamError, (currentError) => {
        error.value = currentError ? t('errors.connection') : '';
    });

    function handleChatEvent(event: ChatStreamEvent) {
        if (event.type === 'snapshot') {
            chat.value = event.chat;
            chatsStore.upsertChat(event.chat);
            messages.value = event.messages;
            return;
        }

        if (event.type === 'message_created') {
            upsertMessage(event.message);
            return;
        }

        if (event.type === 'message_delta') {
            const message = messages.value.find((item) => item.id === event.message_id);
            if (message) {
                const chunk = upsertChunk(message, event.chunk_index, event.chunk_type);
                chunk.content += event.delta;
            }
            return;
        }

        if (event.type === 'message_update_payload') {
            const message = messages.value.find((item) => item.id === event.message_id);
            if (message) {
                const chunk = upsertChunk(message, event.chunk_index, event.chunk_type);
                chunk.payload = event.payload;
            }
            return;
        }

        if (event.type === 'message_done') {
            const message = messages.value.find((item) => item.id === event.message_id);
            if (message) {
                message.status = event.status;
            }
            messageDoneCallbacks.forEach((cb) => cb(message));
            return;
        }

        if (event.type === 'error') {
            error.value = event.message;
        }
    }

    function upsertMessage(message: ChatMessage) {
        const index = messages.value.findIndex((item) => item.id === message.id);
        if (index === -1) {
            messages.value.push(message);
        } else {
            messages.value[index] = message;
        }
    }

    function upsertChunk(
        message: ChatMessage,
        chunkIndex: number,
        chunkType: ChatMessage['chunks'][number]['type'],
    ) {
        let chunk = message.chunks.find((item) => item.index === chunkIndex);
        if (!chunk) {
            chunk = {
                index: chunkIndex,
                type: chunkType,
                content: '',
            };
            message.chunks.push(chunk);
            message.chunks.sort((a, b) => a.index - b.index);
        }
        return chunk;
    }

    async function sendMessage(content: string): Promise<boolean> {
        if (!connected.value) {
            return false;
        }

        try {
            await createChatMessage(String(toValue(chatId)), content);
            error.value = '';
            return true;
        } catch (err) {
            error.value = err instanceof Error ? err.message : t('errors.connection');
            return false;
        }
    }

    function onMessageDone(callback: MessageDoneCallback) {
        messageDoneCallbacks.add(callback);
    }

    watch(
        () => toValue(chatId),
        () => {
            chat.value = null;
            messages.value = [];
        },
        { immediate: true },
    );

    return {
        chat,
        connected,
        error,
        messages,
        sendMessage,
        onMessageDone,
    };
}
