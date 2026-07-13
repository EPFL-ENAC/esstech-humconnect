import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import { useAuthStore } from 'src/stores/auth';
import type {
    CreateChatMessageRequest,
    ChatSession,
    CreateChatResponse,
    ListChatsResponse,
} from 'src/utils/model';

export async function createChat(): Promise<string> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(`${baseUrl}/chats`, {
        method: 'POST',
    });

    if (!response.ok) {
        throw new Error(t('errors.createChat'));
    }

    const responsePayload = (await response.json()) as CreateChatResponse;
    return responsePayload.id;
}

export async function listChats(): Promise<ChatSession[]> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const url = new URL(`${baseUrl}/chats`);

    const response = await authStore.fetchApi(url);
    if (!response.ok) {
        throw new Error(t('errors.loadChats'));
    }

    const payload = (await response.json()) as ListChatsResponse;
    return payload.chats;
}

export async function createChatMessage(chatId: string, content: string): Promise<void> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const payload: CreateChatMessageRequest = { content };
    const response = await authStore.fetchApi(`${baseUrl}/chats/${chatId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(t('errors.connection'));
    }
}

export function chatEventStreamUrl(chatId: string): string {
    return `${baseUrl}/chats/${chatId}/events`;
}
