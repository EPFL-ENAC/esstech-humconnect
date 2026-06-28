export type ChatMessageRole = 'user' | 'assistant';
export type ChatMessageStatus = 'complete' | 'streaming' | 'interrupted' | 'error';
export type ChatMessageChunkType = 'message_content' | 'reasoning_text' | 'tool_call';
export type ToolCallStatus = 'running' | 'finished' | 'failed';

export interface ToolCallPayload {
    tool_name: string;
    tool_label: string;
    call_id: string;
    arguments: Record<string, unknown> | null;
    status: ToolCallStatus;
    answer: string | null;
    error: string | null;
}

export interface ChatMessageChunk {
    index: number;
    type: ChatMessageChunkType;
    content: string;
    payload?: ToolCallPayload | null;
}

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
    chunks: ChatMessageChunk[];
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
    chunk_index: number;
    chunk_type: ChatMessageChunkType;
    delta: string;
}

export interface MessageUpdatePayloadEvent {
    type: 'message_update_payload';
    message_id: string;
    chunk_index: number;
    chunk_type: ChatMessageChunkType;
    payload: ToolCallPayload;
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
    | MessageUpdatePayloadEvent
    | MessageDoneEvent
    | ChatErrorEvent;

export type ChatClientEvent = UserMessageEvent;
export type ChatSession = ChatSessionResponse;
export type ChatMessage = ChatMessageResponse;
