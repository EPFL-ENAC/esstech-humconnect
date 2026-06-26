import { onBeforeUnmount, ref, toValue, watch, type MaybeRefOrGetter } from 'vue';
import {
    chatWebSocketUrl,
    type ChatClientEvent,
    type ChatMessage,
    type ChatSession,
    type ChatSocketEvent,
} from 'src/utils/chatApi';
import { getClientId } from 'src/utils/clientId';
import { useChatsStore } from 'src/stores/chats';

type ChatId = string | number;
type MessageDoneCallback = (message: ChatMessage | undefined) => void;

export function useChat(chatId: MaybeRefOrGetter<ChatId>) {
    const clientId = getClientId();
    const chatsStore = useChatsStore();
    const chat = ref<ChatSession | null>(null);
    const connected = ref(false);
    const error = ref('');
    const messages = ref<ChatMessage[]>([]);

    const messageDoneCallbacks = new Set<MessageDoneCallback>();
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let shouldReconnect = true;

    function connectSocket({ reset = false } = {}) {
        const currentChatId = String(toValue(chatId));
        clearReconnectTimer();
        connected.value = false;
        const previousSocket = socket;
        socket = null;
        previousSocket?.close();

        if (reset) {
            chat.value = null;
            messages.value = [];
        }

        if (!currentChatId) {
            return;
        }

        const nextSocket = new WebSocket(chatWebSocketUrl(currentChatId, clientId));
        socket = nextSocket;

        nextSocket.addEventListener('open', () => {
            if (socket !== nextSocket) {
                return;
            }
            connected.value = true;
            error.value = '';
        });

        nextSocket.addEventListener('message', (event) => {
            if (socket !== nextSocket) {
                return;
            }
            const payload = JSON.parse(String(event.data)) as ChatSocketEvent;
            handleSocketEvent(payload);
        });

        nextSocket.addEventListener('close', () => {
            if (socket !== nextSocket) {
                return;
            }
            connected.value = false;
            if (shouldReconnect) {
                reconnectTimer = window.setTimeout(connectSocket, 1000);
            }
        });

        nextSocket.addEventListener('error', () => {
            if (socket !== nextSocket) {
                return;
            }
            error.value = 'Connection error.';
        });
    }

    function handleSocketEvent(event: ChatSocketEvent) {
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
                message.content += event.delta;
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

    function sendEvent(event: ChatClientEvent): boolean {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return false;
        }

        socket.send(JSON.stringify(event));
        return true;
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
            connectSocket({ reset: true });
        },
        { immediate: true },
    );

    onBeforeUnmount(() => {
        shouldReconnect = false;
        clearReconnectTimer();
        socket?.close();
        socket = null;
    });

    return {
        chat,
        connected,
        error,
        messages,
        sendEvent,
        onMessageDone,
    };
}
