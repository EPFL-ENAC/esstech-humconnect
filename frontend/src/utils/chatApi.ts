import { baseUrl } from 'src/boot/api';

export interface ChatSession {
    id: string;
    client_id: string;
    title: string | null;
    created_at: string;
    updated_at: string;
}

export interface ChatMessage {
    id: string;
    chat_id: string;
    role: 'user' | 'assistant';
    content: string;
    status: 'complete' | 'streaming' | 'interrupted' | 'error';
    created_at: string;
    updated_at: string;
}

export interface ChatSnapshot {
    type: 'snapshot';
    chat: ChatSession;
    messages: ChatMessage[];
}

export type ChatSocketEvent =
    | ChatSnapshot
    | { type: 'message_created'; message: ChatMessage }
    | { type: 'message_delta'; message_id: string; delta: string }
    | { type: 'message_done'; message_id: string; status: ChatMessage['status'] }
    | { type: 'error'; message: string };

export type ChatClientEvent = { type: 'user_message'; content: string };

export async function createChat(clientId: string): Promise<string> {
    const response = await fetch(`${baseUrl}/chats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId }),
    });

    if (!response.ok) {
        throw new Error('Could not create chat.');
    }

    const payload = (await response.json()) as { id: string };
    return payload.id;
}

export async function listChats(clientId: string): Promise<ChatSession[]> {
    const url = new URL(`${baseUrl}/chats`);
    url.searchParams.set('client_id', clientId);

    const response = await fetch(url);
    if (!response.ok) {
        throw new Error('Could not load chats.');
    }

    const payload = (await response.json()) as { chats: ChatSession[] };
    return payload.chats;
}

export function chatWebSocketUrl(chatId: string, clientId: string): string {
    const url = new URL(`${baseUrl}/chats/${chatId}/ws`);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.searchParams.set('client_id', clientId);
    return url.toString();
}
