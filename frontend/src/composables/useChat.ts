import { onBeforeUnmount, ref, toValue, watch, type MaybeRefOrGetter } from 'vue';
import { chatEventStreamUrl, createChatMessage } from 'src/utils/chatApi';
import { authHeaders } from 'src/utils/apiFetch';
import type { ChatMessage, ChatSession, ChatStreamEvent } from 'src/utils/model';
import { getI18nT } from 'src/utils/i18n';
import { useChatsStore } from 'src/stores/chats';

type ChatId = string | number;
type MessageDoneCallback = (message: ChatMessage | undefined) => void;

export function useChat(chatId: MaybeRefOrGetter<ChatId>) {
    const t = getI18nT();
    const chatsStore = useChatsStore();
    const chat = ref<ChatSession | null>(null);
    const connected = ref(false);
    const error = ref('');
    const messages = ref<ChatMessage[]>([]);

    const messageDoneCallbacks = new Set<MessageDoneCallback>();
    let abortController: AbortController | null = null;
    let reconnectTimer: number | undefined;
    let shouldReconnect = true;
    let streamGeneration = 0;

    function connectStream({ reset = false } = {}) {
        const currentChatId = String(toValue(chatId));
        streamGeneration += 1;
        clearReconnectTimer();
        connected.value = false;
        abortController?.abort();
        abortController = null;

        if (reset) {
            chat.value = null;
            messages.value = [];
        }

        if (!currentChatId) {
            return;
        }

        abortController = new AbortController();
        void readEventStream(currentChatId, abortController, streamGeneration);
    }

    async function readEventStream(
        currentChatId: string,
        currentAbortController: AbortController,
        generation: number,
    ) {
        try {
            const response = await fetch(chatEventStreamUrl(currentChatId), {
                headers: {
                    Accept: 'text/event-stream',
                    ...(await authHeaders()),
                },
                signal: currentAbortController.signal,
            });

            if (!response.ok || !response.body) {
                throw new Error(t('errors.connection'));
            }

            connected.value = true;
            error.value = '';

            await readSseFrames(response.body, (event) => {
                if (abortController !== currentAbortController || streamGeneration !== generation) {
                    return;
                }
                handleChatEvent(event);
            });
        } catch (err) {
            if (!currentAbortController.signal.aborted) {
                error.value = err instanceof Error ? err.message : t('errors.connection');
            }
        } finally {
            if (abortController === currentAbortController) {
                connected.value = false;
                abortController = null;
                if (shouldReconnect) {
                    reconnectTimer = window.setTimeout(() => connectStream(), 1000);
                }
            }
        }
    }

    async function readSseFrames(
        body: ReadableStream<Uint8Array>,
        onEvent: (event: ChatStreamEvent) => void,
    ) {
        const reader = body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split(/\r?\n\r?\n/);
            buffer = frames.pop() ?? '';

            frames.forEach((frame) => {
                const data = frame
                    .split(/\r?\n/)
                    .filter((line) => line.startsWith('data:'))
                    .map((line) => line.slice(5).trimStart())
                    .join('\n');

                if (data) {
                    onEvent(JSON.parse(data) as ChatStreamEvent);
                }
            });
        }

        buffer += decoder.decode();
    }

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

    function clearReconnectTimer() {
        if (reconnectTimer !== undefined) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = undefined;
        }
    }

    watch(
        () => toValue(chatId),
        () => {
            shouldReconnect = true;
            connectStream({ reset: true });
        },
        { immediate: true },
    );

    onBeforeUnmount(() => {
        shouldReconnect = false;
        clearReconnectTimer();
        abortController?.abort();
        abortController = null;
    });

    return {
        chat,
        connected,
        error,
        messages,
        sendMessage,
        onMessageDone,
    };
}
