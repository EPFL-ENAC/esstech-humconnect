from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from openai.types.responses import EasyInputMessageParam
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, Relationship, SQLModel

MESSAGE_ROLE_ASSISTANT = "assistant"
MESSAGE_ROLE_USER = "user"

MESSAGE_STATUS_COMPLETE = "complete"
MESSAGE_STATUS_ERROR = "error"
MESSAGE_STATUS_INTERRUPTED = "interrupted"
MESSAGE_STATUS_STREAMING = "streaming"

CHUNK_TYPE_MESSAGE_CONTENT = "message_content"
CHUNK_TYPE_REASONING_TEXT = "reasoning_text"


def utc_now() -> datetime:
    return datetime.now(UTC)


class ChatSession(SQLModel, table=True):
    __tablename__ = "chatsession"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    client_id: str = Field(index=True)
    title: str | None = None
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    messages: list["Message"] = Relationship(back_populates="chat")

    def update_title(self, new_title: str) -> None:
        self.title = new_title
        self.updated_at = utc_now()


class Message(SQLModel, table=True):
    __tablename__ = "message"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chat_id: UUID = Field(foreign_key="chatsession.id", index=True)
    role: str = Field(index=True)
    chunks: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    status: str = Field(index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    chat: ChatSession = Relationship(back_populates="messages")

    @staticmethod
    def create_user_message(chat_id: UUID, content: str) -> "Message":
        return Message(
            chat_id=chat_id,
            role=MESSAGE_ROLE_USER,
            chunks=[
                ChatMessageChunk.create(
                    0, CHUNK_TYPE_MESSAGE_CONTENT, content
                ).model_dump(mode="json")
            ],
            status=MESSAGE_STATUS_COMPLETE,
        )

    @staticmethod
    def from_response(response: "ChatMessageResponse") -> "Message":
        return Message(
            id=response.id,
            chat_id=response.chat_id,
            role=response.role,
            chunks=[chunk.model_dump(mode="json") for chunk in response.chunks],
            status=response.status,
            created_at=response.created_at,
            updated_at=response.updated_at,
        )

    def update_chunks_status(
        self, new_chunks: list["ChatMessageChunk"], new_status: str | None
    ) -> None:
        self.chunks = [chunk.model_dump(mode="json") for chunk in new_chunks]
        if new_status is not None:
            self.status = new_status

        self.updated_at = utc_now()


MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["complete", "streaming", "interrupted", "error"]
MessageChunkType = Literal["message_content", "reasoning_text"]


class ChatMessageChunk(BaseModel):
    index: int
    type: MessageChunkType
    content: str

    @staticmethod
    def create(
        chunk_index: int, chunk_type: MessageChunkType, content: str = ""
    ) -> "ChatMessageChunk":
        return ChatMessageChunk(index=chunk_index, type=chunk_type, content=content)

    def append(self, delta: str) -> None:
        self.content += delta


class CreateChatRequest(BaseModel):
    client_id: str = PydanticField(min_length=1, max_length=256)


class CreateChatResponse(BaseModel):
    id: UUID


class ChatSessionResponse(BaseModel):
    id: UUID
    client_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_db_model(chat: ChatSession) -> "ChatSessionResponse":
        return ChatSessionResponse(
            id=chat.id,
            client_id=chat.client_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )


class ChatMessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    role: MessageRole
    chunks: list[ChatMessageChunk]
    status: MessageStatus
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_db_model(message: Message) -> "ChatMessageResponse":
        return ChatMessageResponse(
            id=message.id,
            chat_id=message.chat_id,
            role=cast(MessageRole, message.role),
            chunks=[ChatMessageChunk.model_validate(chunk) for chunk in message.chunks],
            status=cast(MessageStatus, message.status),
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    @staticmethod
    def make_assistant_message(
        chat_id: UUID,
        chunk_index: int | None = None,
        chunk_type: MessageChunkType | None = None,
        content: str = "",
    ) -> "ChatMessageResponse":
        created_at = utc_now()
        chunks = []
        if chunk_index is not None and chunk_type is not None:
            chunks.append(ChatMessageChunk.create(chunk_index, chunk_type, content))

        return ChatMessageResponse(
            id=uuid4(),
            chat_id=chat_id,
            role=MESSAGE_ROLE_ASSISTANT,
            chunks=chunks,
            status=MESSAGE_STATUS_STREAMING,
            created_at=created_at,
            updated_at=created_at,
        )

    def append_chunk_delta(
        self, chunk_index: int, chunk_type: MessageChunkType, delta: str
    ) -> int:
        if (
            len(self.chunks) > chunk_index
            and self.chunks[chunk_index].type == chunk_type
        ):
            self.chunks[chunk_index].append(delta)
            self.updated_at = utc_now()
            return chunk_index

        chunk = ChatMessageChunk.create(chunk_index, chunk_type, delta)
        self.chunks.append(chunk)
        self.chunks.sort(key=lambda item: item.index)
        self.updated_at = utc_now()
        return chunk.index

    def content_for_model(self) -> str:
        return "".join(
            chunk.content
            for chunk in self.chunks
            if chunk.type == CHUNK_TYPE_MESSAGE_CONTENT
        )

    def to_ai_model_input(self) -> EasyInputMessageParam:
        return {
            "role": self.role,
            "content": self.content_for_model(),
        }

    def update_status(self, new_status: MessageStatus) -> None:
        self.status = new_status
        self.updated_at = utc_now()


class ListChatsResponse(BaseModel):
    chats: list[ChatSessionResponse]


class ChatSnapshotResponse(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    chat: ChatSessionResponse
    messages: list[ChatMessageResponse]


class MessageCreatedEvent(BaseModel):
    type: Literal["message_created"] = "message_created"
    message: ChatMessageResponse


class MessageDeltaEvent(BaseModel):
    type: Literal["message_delta"] = "message_delta"
    message_id: UUID
    chunk_index: int
    chunk_type: MessageChunkType
    delta: str


class MessageDoneEvent(BaseModel):
    type: Literal["message_done"] = "message_done"
    message_id: UUID
    status: MessageStatus


class ChatErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class UserMessageEvent(BaseModel):
    type: Literal["user_message"] = "user_message"
    content: str
