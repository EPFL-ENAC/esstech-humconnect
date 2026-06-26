from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ChatSession(SQLModel, table=True):
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


class Message(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chat_id: UUID = Field(foreign_key="chatsession.id", index=True)
    role: str = Field(index=True)
    content: str = ""
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


MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["complete", "streaming", "interrupted", "error"]


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


class ChatMessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime
    updated_at: datetime


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
