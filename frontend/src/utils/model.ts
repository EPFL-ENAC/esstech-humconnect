export type ChatMessageRole = 'user' | 'assistant';
export type ChatMessageStatus = 'complete' | 'streaming' | 'interrupted' | 'error';

export interface CreateChatRequest {
    client_id: string;
}

export interface CreateChatResponse {
    id: string;
}

export interface ChatSessionResponse {
    id: string;
    client_id: string;
    title: string | null;
    created_at: string;
    updated_at: string;
}

export interface ChatMessageResponse {
    id: string;
    chat_id: string;
    role: ChatMessageRole;
    content: string;
    status: ChatMessageStatus;
    created_at: string;
    updated_at: string;
}

export interface ListChatsResponse {
    chats: ChatSessionResponse[];
}

export interface ChatSnapshotResponse {
    type: 'snapshot';
    chat: ChatSessionResponse;
    messages: ChatMessageResponse[];
}

export interface MessageCreatedEvent {
    type: 'message_created';
    message: ChatMessageResponse;
}

export interface MessageDeltaEvent {
    type: 'message_delta';
    message_id: string;
    delta: string;
}

export interface MessageDoneEvent {
    type: 'message_done';
    message_id: string;
    status: ChatMessageStatus;
}

export interface ChatErrorEvent {
    type: 'error';
    message: string;
}

export interface UserMessageEvent {
    type: 'user_message';
    content: string;
}

export type ChatSocketEvent =
    | ChatSnapshotResponse
    | MessageCreatedEvent
    | MessageDeltaEvent
    | MessageDoneEvent
    | ChatErrorEvent;

export type ChatClientEvent = UserMessageEvent;
export type ChatSession = ChatSessionResponse;
export type ChatMessage = ChatMessageResponse;
