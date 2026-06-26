import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import type {
    ChatSession,
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
} from 'src/utils/model';

export async function createChat(clientId: string): Promise<string> {
    const t = getI18nT();
    const payload: CreateChatRequest = { client_id: clientId };
    const response = await fetch(`${baseUrl}/chats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(t('errors.createChat'));
    }

    const responsePayload = (await response.json()) as CreateChatResponse;
    return responsePayload.id;
}

export async function listChats(clientId: string): Promise<ChatSession[]> {
    const t = getI18nT();
    const url = new URL(`${baseUrl}/chats`);
    url.searchParams.set('client_id', clientId);

    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(t('errors.loadChats'));
    }

    const payload = (await response.json()) as ListChatsResponse;
    return payload.chats;
}

export function chatWebSocketUrl(chatId: string, clientId: string): string {
    const url = new URL(`${baseUrl}/chats/${chatId}/ws`);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.searchParams.set('client_id', clientId);
    return url.toString();
}
