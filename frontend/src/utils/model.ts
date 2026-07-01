export type ChatMessageRole = 'user' | 'assistant';
export type ChatMessageStatus = 'complete' | 'streaming' | 'interrupted' | 'error';
export type ChatMessageChunkType = 'message_content' | 'reasoning_text' | 'tool_call';
export type ToolCallStatus = 'running' | 'finished' | 'failed';
export type ProfessionCategory =
    | 'medical_clinical'
    | 'community_health'
    | 'wash'
    | 'logistics_supply'
    | 'surveillance_epidemiology'
    | 'coordination_cluster'
    | 'safe_burial_community_response'
    | 'biomedical_equipment'
    | 'infrastructure_energy'
    | 'hq_programme_referent'
    | 'local_ngo_partner'
    | 'other';

export type LanguageCode =
    | 'ar'
    | 'bn'
    | 'de'
    | 'en'
    | 'es'
    | 'fa'
    | 'fr'
    | 'hi'
    | 'id'
    | 'it'
    | 'ja'
    | 'km'
    | 'ko'
    | 'lo'
    | 'ms'
    | 'my'
    | 'ne'
    | 'pa'
    | 'prs'
    | 'ps'
    | 'pt'
    | 'ru'
    | 'si'
    | 'sw'
    | 'ta'
    | 'te'
    | 'th'
    | 'tl'
    | 'tr'
    | 'uk'
    | 'ur'
    | 'vi'
    | 'yue'
    | 'zh';

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

export interface CreateChatResponse {
    id: string;
}

export interface CreateChatMessageRequest {
    content: string;
}

export interface ChatSessionResponse {
    id: string;
    user_id: string;
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
    initiated_by_user_id: string;
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

export interface UserProfileEditableFields {
    profession: string | null;
    profession_category: ProfessionCategory | null;
    center_address: string | null;
    action_radius_km: number | null;
    location_extra: string | null;
    organisation: string | null;
    mother_tongue: LanguageCode | null;
}

export interface UserProfileResponse extends UserProfileEditableFields {
    id: string;
    email: string | null;
    username: string | null;
    first_name: string | null;
    last_name: string | null;
    created_at: string;
    updated_at: string;
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

export type ChatStreamEvent =
    | ChatSnapshotResponse
    | MessageCreatedEvent
    | MessageDeltaEvent
    | MessageUpdatePayloadEvent
    | MessageDoneEvent
    | ChatErrorEvent;

export type ChatSession = ChatSessionResponse;
export type ChatMessage = ChatMessageResponse;
export type RecordedEvent = RecordedEventResponse;
export type UserProfile = UserProfileResponse;
