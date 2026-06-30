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

export interface CreateChatMessageRequest {
    client_id: string;
    content: string;
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

export interface RecordedEventResponse {
    id: string;
    chat_id: string;
    initiated_by_client_id: string;
    source_message_id: string;
    original_text: string;
    event_name: string;
    event_datetime: string | null;
    event_date_granularity: string;
    event_date_precision: string;
    event_date_input: Record<string, unknown>;
    event_location: Record<string, unknown>;
    tags: string[];
    created_at: string;
}

export interface ListRecordedEventsResponse {
    events: RecordedEventResponse[];
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

export type ChatSocketEvent =
    | ChatSnapshotResponse
    | MessageCreatedEvent
    | MessageDeltaEvent
    | MessageUpdatePayloadEvent
    | MessageDoneEvent
    | ChatErrorEvent;

export type ChatStreamEvent = ChatSocketEvent;
export type ChatSession = ChatSessionResponse;
export type ChatMessage = ChatMessageResponse;
export type RecordedEvent = RecordedEventResponse;
