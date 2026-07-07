import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from openai.types.responses import ResponseFunctionToolCall

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.models.chat import (
    CHUNK_TYPE_MESSAGE_CONTENT,
    CHUNK_TYPE_REASONING_TEXT,
    CHUNK_TYPE_TOOL_CALL,
    ChatMessageChunk,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSnapshotResponse,
    ChatSession,
    Message,
    ToolCallPayload,
    utc_now,
)
from api.models.recorded_event import RecordedEvent
from api.models.user_profile import UserProfile, UserProfilePromptContext
from api.services import chat as chat_service
from api.services import recorded_events as recorded_events_module
from api.services.chat_room import chat_assistant as chat_assistant_module
from api.services.chat_room import chat_db as chat_db_module
from api.services.chat_room import humconnect_assistant as humconnect_assistant_module
from api.services.chat_room.tools import events as events_tool_module
from api.services.chat_room.tools import (
    humanitarian_context as humanitarian_context_tool_module,
)
from api.services.chat_room.tools import meditron as meditron_tool_module
from api.services.chat_room.tools import natural_events as natural_events_tool_module
from api.services.chat_room.chat_assistant import (
    AssistantStreamChunkDelta,
    AssistantStreamPayloadUpdate,
)
from api.services.chat_room.tools import (
    ASK_MEDITRON_TOOL,
    GET_HUMANITARIAN_CONTEXT_TOOL,
    GET_NATURAL_EVENTS_CONTEXT_TOOL,
    RECALL_EVENTS_TOOL,
    RECORD_EVENT_TOOL,
    ToolExecutionContext,
    ToolCallInputItem,
    ToolCallOutput,
)
from api.services.chat import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_ERROR,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_STREAMING,
    ChatRoomRegistry,
    ChatRoomService,
    HumConnectAssistant,
    PersistentChatMessagesHistory,
    PlaceholderChatAssistant,
    mark_stale_streaming_messages_interrupted,
)

TEST_USER_ID = uuid4()


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeAsyncSession:
    commit_count = 0
    instances = []
    last_query = None
    rows = {
        ChatSession: {},
        Message: {},
        RecordedEvent: {},
    }

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.local_commit_count = 0
        self.added = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, row_id):
        return self.rows[model].get(row_id)

    async def exec(self, query):
        self.__class__.last_query = query
        query_text = str(query)
        if "chatsession" in query_text:
            return FakeResult(list(self.rows[ChatSession].values()))
        if "recordedevent" in query_text:
            events = list(self.rows[RecordedEvent].values())
            events.sort(key=lambda event: event.created_at, reverse=True)
            return FakeResult(events)

        messages = list(self.rows[Message].values())
        if "WHERE message.status" in query_text:
            messages = [
                message
                for message in messages
                if message.status == MESSAGE_STATUS_STREAMING
            ]
        messages.sort(key=lambda message: message.created_at)
        return FakeResult(messages)

    def add(self, row):
        self.added.append(row)
        if isinstance(row, ChatSession):
            self.rows[ChatSession][row.id] = row
        if isinstance(row, Message):
            self.rows[Message][row.id] = row
        if isinstance(row, RecordedEvent):
            self.rows[RecordedEvent][row.id] = row

    async def commit(self):
        self.local_commit_count += 1
        self.__class__.commit_count += 1

    async def refresh(self, row):
        return None

    @classmethod
    def reset(cls):
        cls.commit_count = 0
        cls.instances = []
        cls.last_query = None
        cls.rows = {
            ChatSession: {},
            Message: {},
            RecordedEvent: {},
        }


class FakeHistory:
    def __init__(self):
        self.created_turns = []
        self.chat_history = []
        self.progress_tokens = []
        self.payload_updates = []
        self.completed = False
        self.failed = False
        self.active = True
        self.active_response_message_id = None
        self.started_message = None
        self.snapshot = None

    async def user_has_access(self, user_id):
        return user_id == TEST_USER_ID

    async def build_snapshot(
        self, user_id, *, interrupt_stale_streaming_messages=True
    ):
        return self.snapshot

    async def get_assistant_chat_history(
        self, *, interrupt_stale_streaming_messages=True
    ):
        return list(self.chat_history)

    async def submit_question(self, user_id, question):
        self.created_turns.append((user_id, question))
        chat_id = uuid4()
        user_message = Message.create_user_message(chat_id, question)
        return ChatMessageResponse.from_db_model(user_message)

    async def start_response(self):
        if self.started_message is not None:
            return self.started_message

        self.active_response_message_id = uuid4()
        created_at = utc_now()
        self.started_message = ChatMessageResponse(
            id=self.active_response_message_id,
            chat_id=uuid4(),
            role=MESSAGE_ROLE_ASSISTANT,
            chunks=[],
            status=MESSAGE_STATUS_STREAMING,
            created_at=created_at,
            updated_at=created_at,
        )
        return self.started_message

    async def response_progress(self, chunk_index, chunk_type, delta):
        self.progress_tokens.append((chunk_index, chunk_type, delta))
        if self.active_response_message_id is None:
            return None
        return chat_db_module.ResponseProgressResult(chunk_index=chunk_index)

    async def response_payload_update(self, chunk_index, chunk_type, payload):
        self.payload_updates.append((chunk_index, chunk_type, payload))
        if self.active_response_message_id is None:
            return None
        return chat_db_module.ResponseProgressResult(chunk_index=chunk_index)

    async def complete_response(self):
        self.completed = True
        self.active = False

    async def fail_response(self):
        self.failed = True
        self.active = False


class FakeAssistant:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    async def stream_response(self, chat_history, question, tool_context=None):
        self.calls.append((list(chat_history), question, tool_context))
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            if isinstance(
                chunk, AssistantStreamChunkDelta | AssistantStreamPayloadUpdate
            ):
                yield chunk
            else:
                yield AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, chunk)


async def start_and_wait_for_response(room, chat_history=None, question=""):
    await room._start_assistant_response(chat_history or [], question)
    task = room._generation_task
    assert task is not None
    await task


async def collect_events_during_response(room, chat_history=None, question=""):
    events = []

    async def collect_events():
        async for event in room.subscribe():
            events.append(event)

    collector = asyncio.create_task(collect_events())
    await asyncio.sleep(0)
    try:
        await start_and_wait_for_response(room, chat_history, question)
        return events
    finally:
        collector.cancel()
        try:
            await collector
        except asyncio.CancelledError:
            pass


async def collect_room_events_after(action, room, event_count=1):
    events = []

    async def collect_events():
        async for event in room.subscribe():
            events.append(event)
            if len(events) >= event_count:
                break

    collector = asyncio.create_task(collect_events())
    await asyncio.sleep(0)
    try:
        await action()
        await collector
        return events
    finally:
        if not collector.done():
            collector.cancel()
            try:
                await collector
            except asyncio.CancelledError:
                pass


async def immediate_sleep(delay):
    return None


def install_fake_session(monkeypatch):
    FakeAsyncSession.reset()
    monkeypatch.setattr(chat_db_module, "AsyncSQLModelSession", FakeAsyncSession)
    monkeypatch.setattr(chat_db_module, "get_engine", lambda: object())


def make_chat_and_message():
    chat = ChatSession(user_id=TEST_USER_ID)
    message = Message(
        chat_id=chat.id,
        role=MESSAGE_ROLE_ASSISTANT,
        chunks=[],
        status=MESSAGE_STATUS_STREAMING,
    )
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    FakeAsyncSession.rows[Message][message.id] = message
    return chat, message


def message_content(message, chunk_type=CHUNK_TYPE_MESSAGE_CONTENT):
    return "".join(chunk.content for chunk in message.chunks if chunk.type == chunk_type)


def make_db_message(chat_id, role, content, status):
    return Message(
        chat_id=chat_id,
        role=role,
        chunks=[
            ChatMessageChunk.create(0, CHUNK_TYPE_MESSAGE_CONTENT, content).model_dump(
                mode="json"
            )
        ],
        status=status,
    )


def test_persistent_history_loads_messages_for_snapshot(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    first = make_db_message(chat.id, MESSAGE_ROLE_USER, "First", MESSAGE_STATUS_COMPLETE)
    second = make_db_message(
        chat.id, MESSAGE_ROLE_ASSISTANT, "Second", MESSAGE_STATUS_COMPLETE
    )
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    FakeAsyncSession.rows[Message][first.id] = first
    FakeAsyncSession.rows[Message][second.id] = second
    history = PersistentChatMessagesHistory(chat.id)

    snapshot = asyncio.run(history.build_snapshot(TEST_USER_ID))

    assert snapshot is not None
    assert snapshot.chat.id == chat.id
    assert [message_content(message) for message in snapshot.messages] == [
        "First",
        "Second",
    ]


def test_room_snapshot_preserves_streaming_message_when_generation_is_active(monkeypatch):
    install_fake_session(monkeypatch)
    chat, message = make_chat_and_message()
    room = ChatRoomService(chat.id)

    async def has_active_generation():
        return True

    monkeypatch.setattr(room, "has_active_generation", has_active_generation)

    snapshot = asyncio.run(room.build_snapshot(TEST_USER_ID))

    assert snapshot is not None
    assert message.status == MESSAGE_STATUS_STREAMING
    assert snapshot.messages[0].status == MESSAGE_STATUS_STREAMING
    assert FakeAsyncSession.commit_count == 0


def test_persistent_history_submit_question_writes_user_and_caches_response(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    user_message = asyncio.run(history.submit_question(TEST_USER_ID, "Hello there"))

    snapshot = asyncio.run(history.build_snapshot(TEST_USER_ID))
    assert user_message.role == MESSAGE_ROLE_USER
    assert snapshot is not None
    assert [message_content(message) for message in snapshot.messages] == [
        "Hello there"
    ]
    assert [
        row.role
        for row in FakeAsyncSession.instances[-1].added
        if isinstance(row, Message)
    ] == [MESSAGE_ROLE_USER]
    assert chat.title == "Hello there"
    assert FakeAsyncSession.commit_count == 1


def test_persistent_history_start_response_creates_empty_response_record(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))

    async def run():
        created_message = await history.start_response()
        snapshot = await history.build_snapshot(TEST_USER_ID)
        return created_message, snapshot

    created_message, snapshot = asyncio.run(run())

    assert created_message is not None
    persisted_message = FakeAsyncSession.rows[Message][created_message.id]
    assert persisted_message.chunks == []
    assert persisted_message.status == MESSAGE_STATUS_STREAMING
    assert snapshot is not None
    assert snapshot.messages[-1].chunks == []
    assert FakeAsyncSession.commit_count == 2


def test_persistent_history_response_progress_throttles_after_initial_insert(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))
    chunk_index = 0

    async def run():
        assistant_message = await history.start_response()
        await history.response_progress(chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "a")
        for _ in range(chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE - 1):
            await history.response_progress(
                chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "a"
            )

        snapshot = await history.build_snapshot(TEST_USER_ID)
        assert snapshot is not None
        assert message_content(snapshot.messages[-1]) == "a" * (
            chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE
        )
        assert FakeAsyncSession.commit_count == 3

        await history.response_progress(chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "b")
        return assistant_message

    assistant_message = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.chunks[0]["content"] == (
        "a" * chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE
    )
    assert FakeAsyncSession.commit_count == 3


def test_persistent_history_uses_chunk_index_not_type_to_append(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)
    first_chunk_index = 0
    second_chunk_index = 1

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))

    async def run():
        await history.start_response()
        await history.response_progress(
            first_chunk_index, CHUNK_TYPE_REASONING_TEXT, "First"
        )
        await history.response_progress(
            second_chunk_index, CHUNK_TYPE_REASONING_TEXT, "Second"
        )
        snapshot = await history.build_snapshot(TEST_USER_ID)
        return snapshot

    snapshot = asyncio.run(run())

    assert snapshot is not None
    assistant_message = snapshot.messages[-1]
    assert [
        (chunk.index, chunk.type, chunk.content)
        for chunk in assistant_message.chunks
    ] == [
        (first_chunk_index, CHUNK_TYPE_REASONING_TEXT, "First"),
        (second_chunk_index, CHUNK_TYPE_REASONING_TEXT, "Second"),
    ]


def test_persistent_history_response_payload_update_upserts_chunk(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)
    payload = ToolCallPayload(
        tool_name="dummy_tool",
        tool_label="Dummy tool",
        call_id="call_1",
        arguments={"message": "hello"},
        status="running",
    )

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))

    async def run():
        assistant_message = await history.start_response()
        await history.response_payload_update(0, CHUNK_TYPE_TOOL_CALL, payload)
        snapshot = await history.build_snapshot(TEST_USER_ID)
        return assistant_message, snapshot

    assistant_message, snapshot = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.chunks[0]["content"] == ""
    assert persisted_message.chunks[0]["payload"] == payload.model_dump(mode="json")
    assert snapshot is not None
    assert snapshot.messages[-1].chunks[0].payload == payload


def test_persistent_history_response_payload_update_replaces_payload(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)
    running_payload = ToolCallPayload(
        tool_name="dummy_tool",
        tool_label="Dummy tool",
        call_id="call_1",
        arguments={"message": "hello"},
        status="running",
    )
    finished_payload = ToolCallPayload(
        tool_name="dummy_tool",
        tool_label="Dummy tool",
        call_id="call_1",
        arguments={"message": "hello"},
        status="finished",
        answer="Dummy tool received: hello",
    )

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))

    async def run():
        assistant_message = await history.start_response()
        await history.response_payload_update(0, CHUNK_TYPE_TOOL_CALL, running_payload)
        await history.response_payload_update(0, CHUNK_TYPE_TOOL_CALL, finished_payload)
        snapshot = await history.build_snapshot(TEST_USER_ID)
        return assistant_message, snapshot

    assistant_message, snapshot = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert len(persisted_message.chunks) == 1
    assert persisted_message.chunks[0]["payload"] == finished_payload.model_dump(
        mode="json"
    )
    assert snapshot is not None
    assert snapshot.messages[-1].chunks[0].payload == finished_payload


def test_persistent_history_complete_response_flushes_and_marks_complete(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))
    chunk_index = 0

    async def run():
        assistant_message = await history.start_response()
        await history.response_progress(chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "OK")
        await history.complete_response()
        snapshot = await history.build_snapshot(TEST_USER_ID)
        return assistant_message, snapshot

    assistant_message, snapshot = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.chunks[0]["content"] == "OK"
    assert persisted_message.status == MESSAGE_STATUS_COMPLETE
    assert snapshot is not None
    assert snapshot.messages[-1].status == MESSAGE_STATUS_COMPLETE
    assert FakeAsyncSession.commit_count == 3


def test_persistent_history_fail_response_marks_error_in_db_and_memory(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(user_id=TEST_USER_ID)
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question(TEST_USER_ID, "Hello"))
    chunk_index = 0

    async def run():
        assistant_message = await history.start_response()
        await history.response_progress(
            chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "Nope"
        )
        await history.fail_response()
        snapshot = await history.build_snapshot(TEST_USER_ID)
        return assistant_message, snapshot

    assistant_message, snapshot = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.chunks[0]["content"] == "Nope"
    assert persisted_message.status == MESSAGE_STATUS_ERROR
    assert snapshot is not None
    assert snapshot.messages[-1].status == MESSAGE_STATUS_ERROR
    assert FakeAsyncSession.commit_count == 3


def test_service_handles_user_message_through_history_and_hub(monkeypatch):
    async def run():
        history = FakeHistory()
        started_responses = []
        room = ChatRoomService(
            uuid4(),
            messages_history=history,
        )

        async def start_assistant_response(chat_history, question, tool_context=None):
            started_responses.append((chat_history, question, tool_context))

        monkeypatch.setattr(
            room,
            "_start_assistant_response",
            start_assistant_response,
        )

        async def submit_message():
            await room.handle_user_message(TEST_USER_ID, "Hello there")

        events = await collect_room_events_after(submit_message, room)
        created_events = [
            event for event in events if event["type"] == "message_created"
        ]
        assert history.created_turns == [(TEST_USER_ID, "Hello there")]
        assert len(created_events) == 1
        assert created_events[0]["message"]["role"] == MESSAGE_ROLE_USER
        [(started_history, started_question, tool_context)] = started_responses
        assert started_history == []
        assert started_question == "Hello there"
        assert tool_context is not None
        assert tool_context.chat_id == room.chat_id
        assert tool_context.user_id == TEST_USER_ID
        assert str(tool_context.source_message_id) == created_events[0]["message"]["id"]

    asyncio.run(run())


def test_service_passes_user_profile_context_to_assistant_context(monkeypatch):
    async def run():
        history = FakeHistory()
        started_responses = []
        room = ChatRoomService(
            uuid4(),
            messages_history=history,
        )
        user_profile_context = UserProfilePromptContext(username="field-coordinator")

        async def start_assistant_response(chat_history, question, tool_context=None):
            started_responses.append(tool_context)

        monkeypatch.setattr(
            room,
            "_start_assistant_response",
            start_assistant_response,
        )

        await room.handle_user_message(
            TEST_USER_ID,
            "Hello there",
            user_profile_context=user_profile_context,
        )

        [tool_context] = started_responses
        assert tool_context is not None
        assert tool_context.user_profile_context == user_profile_context

    asyncio.run(run())


def test_service_rejects_second_message_while_generation_is_active(monkeypatch):
    history = FakeHistory()
    room = ChatRoomService(uuid4(), messages_history=history)

    async def has_active_generation():
        return True

    monkeypatch.setattr(room, "has_active_generation", has_active_generation)

    with pytest.raises(RuntimeError, match="already streaming"):
        asyncio.run(room.handle_user_message(TEST_USER_ID, "Hello"))

    assert history.created_turns == []


def test_service_subscription_can_start_with_snapshot():
    history = FakeHistory()
    chat = ChatSession(user_id=TEST_USER_ID)
    history.snapshot = ChatSnapshotResponse(
        chat=ChatSessionResponse.from_db_model(chat),
        messages=[],
    )
    room = ChatRoomService(uuid4(), messages_history=history)

    async def run():
        async for event in room.subscribe(TEST_USER_ID, with_snapshot=True):
            return event

    assert asyncio.run(run()) == history.snapshot.model_dump(mode="json")


def test_service_passes_chat_history_and_question_to_assistant():
    history = FakeHistory()
    history_message = ChatMessageResponse.from_db_model(
        make_db_message(
            uuid4(), MESSAGE_ROLE_USER, "Earlier question", MESSAGE_STATUS_COMPLETE
        )
    )
    history.chat_history = [history_message]
    assistant = FakeAssistant(
        [
            AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, "O"),
            AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, "K"),
        ]
    )
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=assistant,
    )
    asyncio.run(start_and_wait_for_response(room, history.chat_history, "Latest question"))

    assert assistant.calls == [([history_message], "Latest question", None)]
    assert history.progress_tokens == [
        (0, CHUNK_TYPE_MESSAGE_CONTENT, "O"),
        (0, CHUNK_TYPE_MESSAGE_CONTENT, "K"),
    ]


def test_assistant_stream_pushes_every_chunk_and_broadcasts_deltas():
    history = FakeHistory()
    assistant = FakeAssistant(
        [
            AssistantStreamChunkDelta(
                0, CHUNK_TYPE_REASONING_TEXT, "Thinking"
            ),
            AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Hello"),
            AssistantStreamChunkDelta(
                1, CHUNK_TYPE_MESSAGE_CONTENT, " there"
            ),
        ]
    )
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=assistant,
    )
    events = asyncio.run(collect_events_during_response(room, [], "Hello?"))

    chunks = [
        (0, CHUNK_TYPE_REASONING_TEXT, "Thinking"),
        (1, CHUNK_TYPE_MESSAGE_CONTENT, "Hello"),
        (1, CHUNK_TYPE_MESSAGE_CONTENT, " there"),
    ]
    assert history.progress_tokens == chunks
    assert history.completed
    created_event = events[0]
    assert created_event["type"] == "message_created"
    assert created_event["message"]["role"] == MESSAGE_ROLE_ASSISTANT
    assert created_event["message"]["chunks"] == []
    assert events[1]["chunk_type"] == CHUNK_TYPE_REASONING_TEXT
    assert events[1]["chunk_index"] == 0
    assert events[1]["delta"] == "Thinking"
    assert events[2]["chunk_type"] == CHUNK_TYPE_MESSAGE_CONTENT
    assert events[2]["chunk_index"] == 1
    assert events[2]["delta"] == "Hello"
    assert events[3]["chunk_type"] == CHUNK_TYPE_MESSAGE_CONTENT
    assert events[3]["chunk_index"] == events[2]["chunk_index"]
    assert events[3]["delta"] == " there"
    assert events[-1] == {
        "type": "message_done",
        "message_id": created_event["message"]["id"],
        "status": MESSAGE_STATUS_COMPLETE,
    }


def test_assistant_stream_broadcasts_payload_updates():
    history = FakeHistory()
    payload = ToolCallPayload(
        tool_name="dummy_tool",
        tool_label="Dummy tool",
        call_id="call_1",
        arguments={"message": "hello"},
        status="running",
    )
    assistant = FakeAssistant(
        [
            AssistantStreamPayloadUpdate(0, CHUNK_TYPE_TOOL_CALL, payload),
        ]
    )
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=assistant,
    )

    events = asyncio.run(collect_events_during_response(room, [], "Hello?"))

    created_event = events[0]
    assert history.payload_updates == [(0, CHUNK_TYPE_TOOL_CALL, payload)]
    assert events[1] == {
        "type": "message_update_payload",
        "message_id": created_event["message"]["id"],
        "chunk_index": 0,
        "chunk_type": CHUNK_TYPE_TOOL_CALL,
        "payload": payload.model_dump(mode="json"),
    }


def test_assistant_stream_returns_without_done_event_when_no_tokens_are_generated():
    history = FakeHistory()
    assistant = FakeAssistant([])
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=assistant,
    )

    events = asyncio.run(collect_events_during_response(room))

    assert events[0]["type"] == "message_created"
    assert events[0]["message"]["chunks"] == []
    assert events[1] == {
        "type": "message_done",
        "message_id": events[0]["message"]["id"],
        "status": MESSAGE_STATUS_COMPLETE,
    }
    assert history.progress_tokens == []
    assert assistant.calls == [([], "", None)]


def test_assistant_stream_marks_message_error_when_streaming_fails(monkeypatch):
    history = FakeHistory()
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=FakeAssistant(["created", "broken"]),
    )
    original_broadcast = room.broadcast

    async def broadcast(event):
        if event["type"] == "message_delta":
            raise RuntimeError("stream failed")
        await original_broadcast(event)

    monkeypatch.setattr(room, "broadcast", broadcast)

    async def run():
        async def start_response():
            await start_and_wait_for_response(room)

        return await collect_room_events_after(start_response, room, event_count=2)

    events = asyncio.run(run())

    assert history.failed
    assert events[0]["type"] == "message_created"
    assert events[1] == {
        "type": "message_done",
        "message_id": events[0]["message"]["id"],
        "status": MESSAGE_STATUS_ERROR,
    }


def test_assistant_stream_does_not_mark_error_when_done_broadcast_fails(monkeypatch):
    history = FakeHistory()
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=FakeAssistant(["done"]),
    )
    original_broadcast = room.broadcast

    async def broadcast(event):
        if event["type"] == "message_done":
            raise RuntimeError("done broadcast failed")
        await original_broadcast(event)

    monkeypatch.setattr(room, "broadcast", broadcast)

    async def run():
        async def start_response():
            await start_and_wait_for_response(room)

        return await collect_room_events_after(start_response, room, event_count=2)

    with pytest.raises(RuntimeError, match="done broadcast failed"):
        asyncio.run(run())

    assert history.completed
    assert not history.failed


def test_assistant_stream_marks_message_error_when_assistant_fails():
    history = FakeHistory()
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=FakeAssistant([RuntimeError("assistant failed")]),
    )

    events = asyncio.run(collect_events_during_response(room, [], "Hello?"))

    assert history.failed
    assert events[0]["type"] == "message_created"
    assert events[0]["message"]["chunks"] == []
    assert events[1] == {
        "type": "message_done",
        "message_id": events[0]["message"]["id"],
        "status": MESSAGE_STATUS_ERROR,
    }


def test_placeholder_chat_assistant_streams_random_number(monkeypatch):
    monkeypatch.setattr(chat_assistant_module.random, "randint", lambda start, end: 42)
    monkeypatch.setattr(chat_assistant_module.asyncio, "sleep", immediate_sleep)
    assistant = PlaceholderChatAssistant()

    async def run():
        return [
            chunk.content_delta
            async for chunk in assistant.stream_response([], "What number?")
        ]

    assert asyncio.run(run()) == list("Random number: 42")


def test_humconnect_chat_assistant_converts_complete_history_for_model():
    chat_id = uuid4()
    messages = [
        ChatMessageResponse.from_db_model(
            make_db_message(chat_id, MESSAGE_ROLE_USER, "Hello", MESSAGE_STATUS_COMPLETE)
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Hi",
                status=MESSAGE_STATUS_COMPLETE,
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Still typing",
                status=MESSAGE_STATUS_STREAMING,
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Failed",
                status=MESSAGE_STATUS_ERROR,
            )
        ),
    ]

    model_input = HumConnectAssistant.chat_history_to_model_input(messages)

    assert model_input == [
        {
            "role": MESSAGE_ROLE_USER,
            "content": "Hello",
        },
        {
            "role": MESSAGE_ROLE_ASSISTANT,
            "content": "Hi",
        },
    ]


def test_user_profile_prompt_context_formats_prompt_safe_fields():
    profile = UserProfile(
        keycloak_sub="user-1",
        email="field@example.test",
        username=" field-lead ",
        first_name=" Ada ",
        last_name=" Lovelace ",
        profession="Clinician",
        profession_category="medical_clinical",
        center_address="Geneva logistics hub",
        center_latitude=46.2044,
        center_longitude=6.1432,
        action_radius_km=25,
        location_extra="Can cover nearby clinics",
        organisation="HumConnect",
        mother_tongue="en",
    )

    prompt_text = UserProfilePromptContext.from_db_model(profile).to_prompt_text()

    assert "- Name: Ada Lovelace" in prompt_text
    assert "- Username: field-lead" in prompt_text
    assert "- Profession: Clinician" in prompt_text
    assert "- Profession category: medical_clinical" in prompt_text
    assert "- Organisation: HumConnect" in prompt_text
    assert "- Mother tongue: en" in prompt_text
    assert "- Operating location: Geneva logistics hub" in prompt_text
    assert "- Action radius: 25 km" in prompt_text
    assert "- Location notes: Can cover nearby clinics" in prompt_text
    assert "field@example.test" not in prompt_text
    assert "46.2044" not in prompt_text
    assert "6.1432" not in prompt_text


def test_user_profile_prompt_context_omits_empty_fields():
    profile = UserProfile(
        keycloak_sub="user-1",
        username="",
        profession="  ",
    )

    prompt_text = UserProfilePromptContext.from_db_model(profile).to_prompt_text()

    assert prompt_text == ""


def test_humconnect_chat_assistant_streams_openai_text_deltas(monkeypatch):
    class FakeEvent:
        def __init__(
            self,
            event_type,
            delta="",
            item_id=None,
            output_index=0,
            content_index=0,
            item=None,
        ):
            self.type = event_type
            self.delta = delta
            self.item_id = item_id
            self.output_index = output_index
            self.content_index = content_index
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = None

        async def create(self, **kwargs):
            self.create_kwargs = kwargs

            async def stream():
                yield FakeEvent("response.created")
                yield FakeEvent(
                    "response.reasoning_text.delta", "Think", "reasoning-item"
                )
                yield FakeEvent("response.output_text.delta", "Hel", "message-item")
                yield FakeEvent("response.output_text.delta", "lo", "message-item")

            return stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()
    chat_id = uuid4()
    history = [
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_USER,
                content="Earlier question",
                status=MESSAGE_STATUS_COMPLETE,
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Earlier answer",
                status=MESSAGE_STATUS_COMPLETE,
            )
        ),
    ]

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response(history, "Say hello")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamChunkDelta(0, CHUNK_TYPE_REASONING_TEXT, "Think"),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Hel"),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "lo"),
    ]
    assert fake_client.responses.create_kwargs["stream"] is True
    assert [
        tool["name"] for tool in fake_client.responses.create_kwargs["tools"]
    ] == [
        "dummy_tool",
        "ask_meditron",
        "record_event",
        "recall_events",
        "get_natural_events_context",
        "get_humanitarian_context",
    ]
    assert fake_client.responses.create_kwargs["input"] == [
        {
            "role": MESSAGE_ROLE_USER,
            "content": "Earlier question",
        },
        {
            "role": MESSAGE_ROLE_ASSISTANT,
            "content": "Earlier answer",
        },
        {
            "role": "user",
            "content": "Say hello",
        },
    ]


def test_humconnect_chat_assistant_adds_user_profile_to_instructions(monkeypatch):
    class FakeEvent:
        def __init__(self, event_type, delta=""):
            self.type = event_type
            self.delta = delta

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = None

        async def create(self, **kwargs):
            self.create_kwargs = kwargs

            async def stream():
                yield FakeEvent("response.output_text.delta", "Hello")

            return stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()
    tool_context = ToolExecutionContext(
        chat_id=uuid4(),
        user_id=TEST_USER_ID,
        source_message_id=uuid4(),
        user_profile_context=UserProfilePromptContext(
            full_name="Ada Lovelace",
            username="field-lead",
            profession="Clinician",
            center_address="Geneva logistics hub",
        ),
    )

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response(
                [],
                "Say hello",
                tool_context,
            )
        ]

    assert asyncio.run(run()) == [
        AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, "Hello"),
    ]
    instructions = fake_client.responses.create_kwargs["instructions"]
    assert "Current user profile context:" in instructions
    assert "- Name: Ada Lovelace" in instructions
    assert "- Username: field-lead" in instructions
    assert "- Profession: Clinician" in instructions
    assert "- Operating location: Geneva logistics hub" in instructions
    assert "Do not treat it as patient or event information" in instructions


def test_tool_call_output_formats_json_and_reports_success_status():
    success = ToolCallOutput.from_success("Tool finished")
    failure = ToolCallOutput.from_failure("Tool failed")

    assert success.to_json() == '{"ok": true, "result": "Tool finished"}'
    assert success.is_successful() is True
    assert failure.to_json() == '{"ok": false, "error": "Tool failed"}'
    assert failure.is_successful() is False


def test_tool_call_input_item_preserves_function_call_optional_fields():
    function_call = ResponseFunctionToolCall(
        id="item_1",
        arguments='{"message": "hello"}',
        call_id="call_1",
        name="dummy_tool",
        type="function_call",
        status="completed",
    )

    input_item = ToolCallInputItem.from_function_call(function_call)

    assert input_item.to_openai_input_item() == {
        "type": "function_call",
        "id": "item_1",
        "call_id": "call_1",
        "name": "dummy_tool",
        "arguments": '{"message": "hello"}',
        "status": "completed",
    }


def test_ask_meditron_tool_calls_meditron_with_prompt(monkeypatch):
    calls = []

    def fake_ask_meditron(*, prompt, system_prompt):
        calls.append((prompt, system_prompt))
        return "Meditron answer"

    monkeypatch.setattr(meditron_tool_module, "ask_meditron", fake_ask_meditron)

    async def run():
        return await ASK_MEDITRON_TOOL.execute({"prompt": "What is cholera?"})

    assert asyncio.run(run()) == "Meditron answer"
    assert calls == [("What is cholera?", "")]


def test_ask_meditron_tool_passes_system_prompt(monkeypatch):
    calls = []

    def fake_ask_meditron(*, prompt, system_prompt):
        calls.append((prompt, system_prompt))
        return "Clinical answer"

    monkeypatch.setattr(meditron_tool_module, "ask_meditron", fake_ask_meditron)

    async def run():
        return await ASK_MEDITRON_TOOL.execute(
            {
                "prompt": "How should dehydration be assessed?",
                "system_prompt": "Answer concisely.",
            }
        )

    assert asyncio.run(run()) == "Clinical answer"
    assert calls == [("How should dehydration be assessed?", "Answer concisely.")]


@pytest.mark.parametrize("prompt", ["", 123, None])
def test_ask_meditron_tool_rejects_missing_or_empty_prompt(prompt):
    async def run():
        return await ASK_MEDITRON_TOOL.execute({"prompt": prompt})

    with pytest.raises(ValueError, match="non-empty string prompt"):
        asyncio.run(run())


def test_ask_meditron_tool_rejects_non_string_system_prompt():
    async def run():
        return await ASK_MEDITRON_TOOL.execute(
            {"prompt": "What is cholera?", "system_prompt": 42}
        )

    with pytest.raises(ValueError, match="system_prompt to be a string"):
        asyncio.run(run())


class FakeNaturalEventsResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.mark.parametrize(
    "arguments",
    [
        {"center_latitude": -91.0, "center_longitude": 7.0, "radius_km": 10.0},
        {"center_latitude": 46.0, "center_longitude": 181.0, "radius_km": 10.0},
        {"center_latitude": 46.0, "center_longitude": 7.0, "radius_km": 0.0},
        {"center_latitude": 46.0, "center_longitude": 7.0, "radius_km": -1.0},
        {"center_latitude": 46.0, "center_longitude": 7.0, "radius_km": 1000.1},
    ],
)
def test_get_natural_events_context_tool_rejects_invalid_input(arguments):
    async def run():
        return await GET_NATURAL_EVENTS_CONTEXT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_get_natural_events_context_tool_fetches_and_normalizes_events(monkeypatch):
    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        if "eonet" in url:
            return FakeNaturalEventsResponse(
                {
                    "features": [
                        {
                            "id": "EONET_1",
                            "properties": {
                                "id": "EONET_1",
                                "title": "Wildfire near Lausanne",
                                "date": "2026-07-02T12:00:00Z",
                                "categories": [
                                    {"id": "wildfires", "title": "Wildfires"}
                                ],
                                "sources": [{"url": "https://example.test/eonet"}],
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": [7.01, 46.01],
                            },
                        },
                        {
                            "id": "EONET_OUTSIDE",
                            "properties": {
                                "id": "EONET_OUTSIDE",
                                "title": "Distant storm",
                                "date": "2026-07-02T12:00:00Z",
                                "categories": [{"id": "severeStorms"}],
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": [7.0, 48.0],
                            },
                        },
                    ]
                }
            )

        return FakeNaturalEventsResponse(
            {
                "features": [
                    {
                        "id": "us7000abcd",
                        "properties": {
                            "title": "M 4.5 - Switzerland",
                            "type": "earthquake",
                            "time": 1783000000000,
                            "status": "reviewed",
                            "mag": 4.5,
                            "url": "https://example.test/usgs",
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [7.2, 46.2, 10.0],
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(natural_events_tool_module.requests, "get", fake_get)

    async def run():
        return await GET_NATURAL_EVENTS_CONTEXT_TOOL.execute(
            {
                "center_latitude": 46.0,
                "center_longitude": 7.0,
                "radius_km": 100.0,
            }
        )

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "nasa_eonet": 1,
        "usgs_earthquakes": 1,
    }
    assert result["center"] == {
        "latitude": 46.0,
        "longitude": 7.0,
        "radius_km": 100.0,
    }
    assert [event["id"] for event in result["events"]] == [
        "us7000abcd",
        "EONET_1",
    ]
    assert result["events"][0]["provider"] == "USGS Earthquake Catalog"
    assert result["events"][0]["magnitude"] == 4.5
    assert result["events"][1]["provider"] == "NASA EONET"
    assert result["events"][1]["category"] == "Wildfires"
    assert all(event["id"] != "EONET_OUTSIDE" for event in result["events"])

    eonet_url, eonet_params, eonet_timeout = calls[0]
    assert eonet_url.endswith("/events/geojson")
    assert eonet_params["status"] == "open"
    assert eonet_params["limit"] == 20
    assert len(eonet_params["bbox"].split(",")) == 4
    assert eonet_timeout == 5

    usgs_url, usgs_params, usgs_timeout = calls[1]
    assert usgs_url.endswith("/query")
    assert usgs_params["format"] == "geojson"
    assert usgs_params["latitude"] == 46.0
    assert usgs_params["longitude"] == 7.0
    assert usgs_params["maxradiuskm"] == 100.0
    assert usgs_params["orderby"] == "time"
    assert usgs_params["limit"] == 20
    assert usgs_timeout == 5


def test_get_natural_events_context_tool_returns_partial_results(monkeypatch):
    def fake_get(url, *, params, timeout):
        if "eonet" in url:
            raise natural_events_tool_module.requests.RequestException("timeout")

        return FakeNaturalEventsResponse({"features": []})

    monkeypatch.setattr(natural_events_tool_module.requests, "get", fake_get)

    async def run():
        return await GET_NATURAL_EVENTS_CONTEXT_TOOL.execute(
            {
                "center_latitude": 46.0,
                "center_longitude": 7.0,
                "radius_km": 100.0,
            }
        )

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "nasa_eonet": 0,
        "usgs_earthquakes": 0,
    }
    assert result["events"] == []
    assert result["warnings"] == ["NASA EONET could not be reached."]


def test_get_natural_events_context_tool_rejects_both_malformed_provider_payloads(
    monkeypatch,
):
    def fake_get(url, *, params, timeout):
        return FakeNaturalEventsResponse({"not_features": []})

    monkeypatch.setattr(natural_events_tool_module.requests, "get", fake_get)

    async def run():
        return await GET_NATURAL_EVENTS_CONTEXT_TOOL.execute(
            {
                "center_latitude": 46.0,
                "center_longitude": 7.0,
                "radius_km": 100.0,
            }
        )

    with pytest.raises(ValueError, match="malformed natural event data"):
        asyncio.run(run())


class FakeReliefWebResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"country_name": ""},
        {"country_name": "   "},
        {"country_name": 123},
    ],
)
def test_get_humanitarian_context_tool_rejects_invalid_input(arguments):
    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_get_humanitarian_context_tool_fetches_and_normalizes_items(monkeypatch):
    calls = []

    def fake_post(url, *, params, json, timeout):
        calls.append((url, params, json, timeout))
        if url.endswith("/reports"):
            return FakeReliefWebResponse(
                {
                    "data": [
                        {
                            "id": 123,
                            "fields": {
                                "title": "Cholera outbreak update",
                                "url": "https://example.test/report",
                                "date": {
                                    "created": "2026-07-02T12:00:00+00:00",
                                    "original": "2026-07-01T12:00:00+00:00",
                                },
                                "primary_country": [{"name": "Haiti"}],
                                "source": [{"name": "WHO"}],
                                "disaster_type": [{"name": "Epidemic"}],
                                "theme": [{"name": "Health"}],
                                "format": [{"name": "Situation Report"}],
                            },
                        }
                    ]
                }
            )

        return FakeReliefWebResponse(
            {
                "data": [
                    {
                        "id": "dis-1",
                        "fields": {
                            "name": "Haiti: Floods - Jul 2026",
                            "url": "https://example.test/disaster",
                            "date": {"created": "2026-07-01T10:00:00+00:00"},
                            "primary_country": {"name": "Haiti"},
                            "type": [{"name": "Flood"}],
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(humanitarian_context_tool_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": " Haiti "}
        )

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "reports": 1,
        "disasters": 1,
    }
    assert result["country"] == "Haiti"
    assert [item["id"] for item in result["items"]] == ["123", "dis-1"]
    assert result["items"][0] == {
        "provider": "ReliefWeb",
        "type": "report",
        "id": "123",
        "title": "Cholera outbreak update",
        "category": "Epidemic",
        "time": "2026-07-02T12:00:00Z",
        "source_url": "https://example.test/report",
        "sources": ["WHO"],
        "country": "Haiti",
        "location_precision": "country",
    }
    assert result["items"][1] == {
        "provider": "ReliefWeb",
        "type": "disaster",
        "id": "dis-1",
        "title": "Haiti: Floods - Jul 2026",
        "category": "Flood",
        "time": "2026-07-01T10:00:00Z",
        "source_url": "https://example.test/disaster",
        "sources": [],
        "country": "Haiti",
        "location_precision": "country",
    }

    report_url, report_params, report_payload, report_timeout = calls[0]
    assert report_url.endswith("/reports")
    assert report_params == {
        "appname": humanitarian_context_tool_module.config.RELIEFWEB_APP_NAME
    }
    assert report_payload["limit"] == 10
    assert report_payload["sort"] == ["date.created:desc"]
    assert report_payload["query"]["value"].startswith("outbreak epidemic")
    assert report_payload["fields"]["include"] == [
        "id",
        "title",
        "url",
        "date",
        "primary_country",
        "source",
        "disaster",
        "disaster_type",
        "theme",
        "format",
    ]
    assert {
        condition["field"]: condition["value"]
        for condition in report_payload["filter"]["conditions"]
    }["primary_country.name"] == "Haiti"
    report_date_from = {
        condition["field"]: condition["value"]
        for condition in report_payload["filter"]["conditions"]
    }["date.created"]["from"]
    assert "T" in report_date_from
    assert report_date_from.endswith("+00:00")
    assert report_timeout == 5

    disaster_url, disaster_params, disaster_payload, disaster_timeout = calls[1]
    assert disaster_url.endswith("/disasters")
    assert disaster_params == {
        "appname": humanitarian_context_tool_module.config.RELIEFWEB_APP_NAME
    }
    assert "query" not in disaster_payload
    assert disaster_payload["fields"]["include"] == [
        "id",
        "name",
        "url",
        "date",
        "primary_country",
        "type",
        "status",
    ]
    assert {
        condition["field"]: condition["value"]
        for condition in disaster_payload["filter"]["conditions"]
    }["status"] == "current"
    disaster_date_from = {
        condition["field"]: condition["value"]
        for condition in disaster_payload["filter"]["conditions"]
    }["date.created"]["from"]
    assert "T" in disaster_date_from
    assert disaster_date_from.endswith("+00:00")
    assert disaster_timeout == 5


def test_get_humanitarian_context_tool_returns_partial_results(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        if url.endswith("/reports"):
            raise humanitarian_context_tool_module.requests.RequestException("timeout")

        return FakeReliefWebResponse({"data": []})

    monkeypatch.setattr(humanitarian_context_tool_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": "Sudan"}
        )

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "reports": 0,
        "disasters": 0,
    }
    assert result["country"] == "Sudan"
    assert result["items"] == []
    assert result["warnings"] == ["ReliefWeb reports could not be reached."]


def test_get_humanitarian_context_tool_rejects_all_reliefweb_failures(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        raise humanitarian_context_tool_module.requests.RequestException("timeout")

    monkeypatch.setattr(humanitarian_context_tool_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": "Sudan"}
        )

    with pytest.raises(ValueError, match="humanitarian context from ReliefWeb"):
        asyncio.run(run())


def test_get_humanitarian_context_tool_rejects_all_malformed_payloads(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        return FakeReliefWebResponse({"not_data": []})

    monkeypatch.setattr(humanitarian_context_tool_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": "Sudan"}
        )

    with pytest.raises(ValueError, match="malformed humanitarian context data"):
        asyncio.run(run())


def structured_record_event_arguments():
    return {
        "original_text": "My son started coughing 3 days ago",
        "event_name": "Son started coughing",
        "event_date": {
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "relative": {
                "direction": "past",
                "days": 3,
                "precision": "exact",
            },
        },
        "event_location": {"value": None, "precision": "unknown"},
        "tags": ["symptom", "cough"],
    }


RECORDED_EVENT_CHAT_ID = uuid4()
RECORDED_EVENT_SOURCE_MESSAGE_ID = uuid4()


def record_event_tool_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        chat_id=RECORDED_EVENT_CHAT_ID,
        user_id=TEST_USER_ID,
        source_message_id=RECORDED_EVENT_SOURCE_MESSAGE_ID,
    )


def configure_recorded_event_service(
    monkeypatch,
    *,
    now: datetime | None = None,
) -> None:
    fixed_now = now or datetime(2026, 6, 29, 12, 0, tzinfo=UTC)

    def service_factory():
        return recorded_events_module.RecordedEventService(
            session_factory=FakeAsyncSession,
            engine_factory=lambda: object(),
            now_factory=lambda: fixed_now,
        )

    monkeypatch.setattr(events_tool_module, "RecordedEventService", service_factory)


def recorded_events() -> list[RecordedEvent]:
    return list(FakeAsyncSession.rows[RecordedEvent].values())


def expected_record_event_tool_output(
    event: RecordedEvent,
) -> str:
    return json.dumps(
        {
            "message": f"Recorded event: {event.event_name}",
            "event": event.model_dump(mode="json"),
        },
        indent=2,
    )


def make_recorded_event(
    *,
    chat_id=RECORDED_EVENT_CHAT_ID,
    original_text="My son started coughing 3 days ago",
    event_name="Son started coughing",
    event_datetime=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    event_location=None,
    tags=None,
    created_at=datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
) -> RecordedEvent:
    return RecordedEvent(
        chat_id=chat_id,
        initiated_by_user_id=TEST_USER_ID,
        source_message_id=RECORDED_EVENT_SOURCE_MESSAGE_ID,
        original_text=original_text,
        event_name=event_name,
        event_datetime=event_datetime,
        event_date_granularity="day" if event_datetime is not None else "unknown",
        event_date_precision="exact" if event_datetime is not None else "unknown",
        event_date_input={
            "kind": "absolute" if event_datetime is not None else "unknown",
            "granularity": "day" if event_datetime is not None else "unknown",
            "precision": "exact" if event_datetime is not None else "unknown",
            "value": event_datetime.date().isoformat()
            if event_datetime is not None
            else None,
            "relative": None,
        },
        event_location=event_location or {"value": None, "precision": "unknown"},
        tags=tags or ["symptom", "cough"],
        created_at=created_at,
    )


def expected_recall_events_tool_output(events: list[RecordedEvent]) -> str:
    return json.dumps(
        {
            "message": f"Recalled {len(events)} event(s).",
            "events": [event.model_dump(mode="json") for event in events],
        },
        indent=2,
    )


def test_recorded_event_service_persists_event_with_initiator_metadata():
    FakeAsyncSession.reset()
    event_input = events_tool_module.RecordEventToolInput.model_validate(
        structured_record_event_arguments()
    )
    service = recorded_events_module.RecordedEventService(
        session_factory=FakeAsyncSession,
        engine_factory=lambda: object(),
        now_factory=lambda: datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
    )

    async def run():
        return await service.record_event_from_tool(
            event_input=event_input,
            chat_id=RECORDED_EVENT_CHAT_ID,
            user_id=TEST_USER_ID,
            source_message_id=RECORDED_EVENT_SOURCE_MESSAGE_ID,
        )

    response = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.chat_id == RECORDED_EVENT_CHAT_ID
    assert persisted_event.initiated_by_user_id == TEST_USER_ID
    assert persisted_event.source_message_id == RECORDED_EVENT_SOURCE_MESSAGE_ID
    assert persisted_event.original_text == "My son started coughing 3 days ago"
    assert persisted_event.event_name == "Son started coughing"
    assert persisted_event.event_datetime == datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    assert persisted_event.event_date_granularity == "day"
    assert persisted_event.event_date_precision == "exact"
    assert persisted_event.event_date_input == {
        "kind": "relative",
        "granularity": "day",
        "precision": "exact",
        "value": None,
        "relative": {
            "direction": "past",
            "years": None,
            "months": None,
            "weeks": None,
            "days": 3,
            "hours": None,
            "minutes": None,
            "precision": "exact",
        },
    }
    assert persisted_event.event_location == {"value": None, "precision": "unknown"}
    assert persisted_event.tags == ["symptom", "cough"]
    assert response == persisted_event


def test_recorded_event_service_builds_user_scoped_filtered_recall_query():
    FakeAsyncSession.reset()
    cough_event = make_recorded_event()
    other_chat_event = make_recorded_event(
        chat_id=uuid4(),
        created_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    FakeAsyncSession.rows[RecordedEvent][cough_event.id] = cough_event
    FakeAsyncSession.rows[RecordedEvent][other_chat_event.id] = other_chat_event

    recall_input = events_tool_module.RecallEventsToolInput.model_validate(
        {
            "keyword": "cough",
            "date_start": "2026-06-20T00:00:00+00:00",
            "date_end": "2026-06-30T00:00:00+00:00",
            "tags": ["symptom"],
            "tag_match": "all",
            "limit": 10,
        }
    )
    service = recorded_events_module.RecordedEventService(
        session_factory=FakeAsyncSession,
        engine_factory=lambda: object(),
    )

    async def run():
        return await service.recall_events_from_tool(
            recall_input=recall_input,
            user_id=TEST_USER_ID,
        )

    assert asyncio.run(run()) == [other_chat_event, cough_event]

    query_text = str(FakeAsyncSession.last_query)
    assert "recordedevent.initiated_by_user_id" in query_text
    assert "WHERE recordedevent.chat_id" not in query_text
    assert "AND recordedevent.chat_id" not in query_text
    assert "recordedevent.event_datetime >= " in query_text
    assert "recordedevent.event_datetime <= " in query_text
    assert "lower(recordedevent.event_name) LIKE lower(" in query_text
    assert "lower(recordedevent.original_text) LIKE lower(" in query_text
    assert "CAST(recordedevent.event_location AS VARCHAR)" in query_text
    assert "CAST(recordedevent.tags AS JSONB)" in query_text
    assert " LIMIT " in query_text


def test_record_event_tool_delegates_to_recorded_event_service(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)

    async def run():
        return await RECORD_EVENT_TOOL.execute(
            structured_record_event_arguments(),
            record_event_tool_context(),
        )

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.chat_id == RECORDED_EVENT_CHAT_ID
    assert persisted_event.initiated_by_user_id == TEST_USER_ID
    assert persisted_event.source_message_id == RECORDED_EVENT_SOURCE_MESSAGE_ID
    assert output == expected_record_event_tool_output(persisted_event)


def test_recall_events_tool_delegates_to_recorded_event_service(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    cough_event = make_recorded_event()
    fever_event = make_recorded_event(
        original_text="My son had a fever yesterday",
        event_name="Son had fever",
        event_datetime=datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
        tags=["symptom", "fever"],
        created_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    FakeAsyncSession.rows[RecordedEvent][cough_event.id] = cough_event
    FakeAsyncSession.rows[RecordedEvent][fever_event.id] = fever_event

    arguments = {
        "keyword": "son",
        "date_start": "2026-06-20T00:00:00+00:00",
        "date_end": "2026-06-30T00:00:00+00:00",
        "tags": ["cough", "fever"],
        "tag_match": "any",
        "limit": 5,
    }

    async def run():
        return await RECALL_EVENTS_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    assert output == expected_recall_events_tool_output([fever_event, cough_event])


def test_recall_events_tool_requires_execution_context(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    cough_event = make_recorded_event()
    FakeAsyncSession.rows[RecordedEvent][cough_event.id] = cough_event

    async def run():
        return await RECALL_EVENTS_TOOL.execute(
            {
                "keyword": "cough",
                "date_start": None,
                "date_end": None,
                "tags": [],
                "tag_match": "all",
                "limit": 10,
            }
        )

    with pytest.raises(ValueError, match="requires chat execution context"):
        asyncio.run(run())


def test_recall_events_tool_rejects_invalid_date_range():
    async def run():
        return await RECALL_EVENTS_TOOL.execute(
            {
                "keyword": None,
                "date_start": "2026-06-30T00:00:00+00:00",
                "date_end": "2026-06-20T00:00:00+00:00",
                "tags": [],
                "tag_match": "all",
                "limit": 10,
            },
            record_event_tool_context(),
        )

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_record_event_tool_schema_exposes_relative_date_shape():
    parameters = RECORD_EVENT_TOOL.definition["parameters"]
    defs = parameters["$defs"]
    event_date_schema = defs["RecordEventDateInput"]
    relative_schema = defs["RecordEventRelativeDateInput"]

    assert RECORD_EVENT_TOOL.definition["type"] == "function"
    assert RECORD_EVENT_TOOL.definition["strict"] is True
    assert parameters["additionalProperties"] is False
    assert event_date_schema["additionalProperties"] is False
    assert relative_schema["additionalProperties"] is False
    assert parameters["properties"]["event_date"] == {
        "$ref": "#/$defs/RecordEventDateInput"
    }
    assert event_date_schema["required"] == [
        "kind",
        "granularity",
        "precision",
        "value",
        "relative",
    ]
    assert relative_schema["required"] == [
        "direction",
        "years",
        "months",
        "weeks",
        "days",
        "hours",
        "minutes",
        "precision",
    ]
    assert parameters["properties"]["original_text"]["description"] == (
        "The exact user text that contains the event."
    )
    assert event_date_schema["properties"]["value"]["description"].startswith(
        "For absolute dates"
    )
    assert relative_schema["properties"]["direction"]["enum"] == ["past", "future"]
    assert relative_schema["properties"]["days"]["anyOf"] == [
        {"minimum": 0, "type": "integer"},
        {"type": "null"},
    ]


def test_record_event_tool_accepts_json_stringified_structured_fields(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = json.dumps(arguments["event_date"])
    arguments["event_location"] = json.dumps(arguments["event_location"])
    arguments["tags"] = json.dumps(arguments["tags"])

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    assert persisted_event.tags == ["symptom", "cough"]
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_requires_execution_context(monkeypatch):
    configure_recorded_event_service(monkeypatch)

    async def run():
        return await RECORD_EVENT_TOOL.execute(structured_record_event_arguments())

    with pytest.raises(ValueError, match="requires chat execution context"):
        asyncio.run(run())


@pytest.mark.parametrize("original_text", ["", "   ", 123, None])
def test_record_event_tool_rejects_missing_or_empty_original_text(original_text):
    arguments = structured_record_event_arguments()
    arguments["original_text"] = original_text

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_accepts_absolute_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "absolute",
        "granularity": "minute",
        "precision": "exact",
        "value": "2026-06-29T08:15:00+02:00",
        "relative": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime is not None
    assert persisted_event.event_datetime.isoformat() == "2026-06-29T08:15:00+02:00"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_absolute_date(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "absolute",
        "granularity": "day",
        "precision": "exact",
        "value": "2026-06-29",
        "relative": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(
        2026, 6, 29, 0, 0, tzinfo=UTC
    )
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_fuzzy_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"]["granularity"] = "week"
    arguments["event_date"]["precision"] = "fuzzy"
    arguments["event_date"]["relative"]["weeks"] = 3
    del arguments["event_date"]["relative"]["days"]
    arguments["event_date"]["relative"]["precision"] = "fuzzy"

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
    assert persisted_event.event_date_precision == "fuzzy"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_sparse_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "relative",
        "granularity": "minute",
        "precision": "exact",
        "relative": {
            "direction": "past",
            "minutes": 30,
            "precision": "exact",
        },
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 11, 30, tzinfo=UTC)
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_strict_nullable_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "relative",
        "granularity": "minute",
        "precision": "exact",
        "value": None,
        "relative": {
            "direction": "past",
            "years": None,
            "months": None,
            "weeks": None,
            "days": None,
            "hours": None,
            "minutes": 30,
            "precision": "exact",
        },
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 11, 30, tzinfo=UTC)
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_unknown_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "unknown",
        "granularity": "unknown",
        "precision": "unknown",
        "value": None,
        "relative": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime is None
    assert output == expected_record_event_tool_output(persisted_event)


@pytest.mark.parametrize(
    "event_date",
    [
        {
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "relative": {
                "direction": "past",
                "precision": "exact",
            },
        },
        {
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "value": None,
            "relative": {
                "direction": "past",
                "years": None,
                "months": None,
                "weeks": None,
                "days": None,
                "hours": None,
                "minutes": None,
                "precision": "exact",
            },
        },
        {
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "relative": {
                "direction": "past",
                "days": -1,
                "precision": "exact",
            },
        },
        {
            "kind": "absolute",
            "granularity": "day",
            "precision": "exact",
            "value": None,
        },
        {
            "kind": "absolute",
            "granularity": "day",
            "precision": "exact",
            "value": "not-a-date",
        },
        {
            "kind": "unknown",
            "granularity": "day",
            "precision": "unknown",
        },
    ],
)
def test_record_event_tool_rejects_invalid_event_date(event_date):
    arguments = structured_record_event_arguments()
    arguments["event_date"] = event_date

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_rejects_non_string_tags():
    arguments = structured_record_event_arguments()
    arguments["tags"] = ["symptom", 123]

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_resolve_relative_datetime_handles_calendar_and_clock_units():
    reference = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)
    relative = events_tool_module.RecordEventRelativeDateInput(
        direction="past",
        years=1,
        months=2,
        weeks=1,
        days=3,
        hours=4,
        minutes=5,
        precision="exact",
    )

    assert (
        relative.resolve_relative_to_datetime(reference).isoformat()
        == "2025-04-19T07:55:00+00:00"
    )


def test_humconnect_chat_assistant_executes_dummy_tool_calls(monkeypatch):
    class FakeEvent:
        def __init__(self, event_type, delta="", item=None):
            self.type = event_type
            self.delta = delta
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = []

        async def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            call_index = len(self.create_kwargs)

            async def first_stream():
                yield FakeEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments='{"message": "hello"}',
                        call_id="call_1",
                        name="dummy_tool",
                        type="function_call",
                        status="completed",
                    ),
                )

            async def second_stream():
                yield FakeEvent("response.output_text.delta", "Done")

            return first_stream() if call_index == 1 else second_stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response([], "Use a tool")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="finished",
                answer="Dummy tool received: hello",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Done"),
    ]

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert second_input[-2] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "dummy_tool",
        "arguments": '{"message": "hello"}',
        "status": "completed",
    }
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok": true, "result": "Dummy tool received: hello"}',
    }


def test_humconnect_chat_assistant_executes_ask_meditron_tool_calls(monkeypatch):
    def fake_ask_meditron(*, prompt, system_prompt):
        assert prompt == "What are cholera symptoms?"
        assert system_prompt == "Answer for a clinician."
        return "Watery diarrhea and dehydration."

    class FakeEvent:
        def __init__(self, event_type, delta="", item=None):
            self.type = event_type
            self.delta = delta
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = []

        async def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            call_index = len(self.create_kwargs)

            async def first_stream():
                yield FakeEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments=(
                            '{"prompt": "What are cholera symptoms?", '
                            '"system_prompt": "Answer for a clinician."}'
                        ),
                        call_id="call_meditron",
                        name="ask_meditron",
                        type="function_call",
                        status="completed",
                    ),
                )

            async def second_stream():
                yield FakeEvent("response.output_text.delta", "Summarized")

            return first_stream() if call_index == 1 else second_stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    monkeypatch.setattr(meditron_tool_module, "ask_meditron", fake_ask_meditron)
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response([], "Use Meditron")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="ask_meditron",
                tool_label="Ask Meditron",
                call_id="call_meditron",
                arguments={
                    "prompt": "What are cholera symptoms?",
                    "system_prompt": "Answer for a clinician.",
                },
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="ask_meditron",
                tool_label="Ask Meditron",
                call_id="call_meditron",
                arguments={
                    "prompt": "What are cholera symptoms?",
                    "system_prompt": "Answer for a clinician.",
                },
                status="finished",
                answer="Watery diarrhea and dehydration.",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Summarized"),
    ]

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert second_input[-2] == {
        "type": "function_call",
        "call_id": "call_meditron",
        "name": "ask_meditron",
        "arguments": (
            '{"prompt": "What are cholera symptoms?", '
            '"system_prompt": "Answer for a clinician."}'
        ),
        "status": "completed",
    }
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_meditron",
        "output": (
            '{"ok": true, "result": "Watery diarrhea and dehydration."}'
        ),
    }


def test_humconnect_chat_assistant_executes_record_event_tool_calls(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    tool_arguments = structured_record_event_arguments()

    class FakeEvent:
        def __init__(self, event_type, delta="", item=None):
            self.type = event_type
            self.delta = delta
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = []

        async def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            call_index = len(self.create_kwargs)

            async def first_stream():
                yield FakeEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments=json.dumps(tool_arguments),
                        call_id="call_record_event",
                        name="record_event",
                        type="function_call",
                        status="completed",
                    ),
                )

            async def second_stream():
                yield FakeEvent("response.output_text.delta", "Noted")

            return first_stream() if call_index == 1 else second_stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response(
                [],
                "Remember this",
                record_event_tool_context(),
            )
        ]

    chunks = asyncio.run(run())
    [persisted_event] = recorded_events()
    expected_output = expected_record_event_tool_output(persisted_event)
    assert chunks == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="record_event",
                tool_label="Record event",
                call_id="call_record_event",
                arguments=tool_arguments,
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="record_event",
                tool_label="Record event",
                call_id="call_record_event",
                arguments=tool_arguments,
                status="finished",
                answer=expected_output,
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Noted"),
    ]
    assert persisted_event.chat_id == RECORDED_EVENT_CHAT_ID
    assert persisted_event.initiated_by_user_id == TEST_USER_ID
    assert persisted_event.source_message_id == RECORDED_EVENT_SOURCE_MESSAGE_ID

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_record_event",
        "output": json.dumps({"ok": True, "result": expected_output}),
    }


def test_humconnect_chat_assistant_reports_invalid_tool_arguments(monkeypatch):
    class FakeEvent:
        def __init__(self, event_type, delta="", item=None):
            self.type = event_type
            self.delta = delta
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = []

        async def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            call_index = len(self.create_kwargs)

            async def first_stream():
                yield FakeEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments='{"message": ""}',
                        call_id="call_1",
                        name="dummy_tool",
                        type="function_call",
                    ),
                )

            async def second_stream():
                yield FakeEvent("response.output_text.delta", "Recovered")

            return first_stream() if call_index == 1 else second_stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response([], "Use a tool")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": ""},
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": ""},
                status="failed",
                error="dummy_tool requires a non-empty string message.",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Recovered"),
    ]
    output = fake_client.responses.create_kwargs[1]["input"][-1]["output"]
    assert '"ok": false' in output
    assert "dummy_tool requires a non-empty string message" in output


def test_humconnect_chat_assistant_reports_malformed_tool_arguments(monkeypatch):
    class FakeEvent:
        def __init__(self, event_type, delta="", item=None):
            self.type = event_type
            self.delta = delta
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = []

        async def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            call_index = len(self.create_kwargs)

            async def first_stream():
                yield FakeEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments="{",
                        call_id="call_1",
                        name="dummy_tool",
                        type="function_call",
                    ),
                )

            async def second_stream():
                yield FakeEvent("response.output_text.delta", "Recovered")

            return first_stream() if call_index == 1 else second_stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response([], "Use a tool")
        ]

    chunks = asyncio.run(run())

    assert chunks[0] == AssistantStreamPayloadUpdate(
        0,
        CHUNK_TYPE_TOOL_CALL,
        ToolCallPayload(
            tool_name="dummy_tool",
            tool_label="Dummy tool",
            call_id="call_1",
            arguments=None,
            status="running",
        ),
    )
    assert isinstance(chunks[1], AssistantStreamPayloadUpdate)
    assert chunks[1].payload.arguments is None
    assert chunks[1].payload.status == "failed"
    assert chunks[1].payload.error is not None
    assert "Expecting property name" in chunks[1].payload.error


def test_humconnect_chat_assistant_reports_unknown_tool(monkeypatch):
    class FakeEvent:
        def __init__(self, event_type, delta="", item=None):
            self.type = event_type
            self.delta = delta
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = []

        async def create(self, **kwargs):
            self.create_kwargs.append(kwargs)
            call_index = len(self.create_kwargs)

            async def first_stream():
                yield FakeEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments='{"message": "hello"}',
                        call_id="call_1",
                        name="missing_tool",
                        type="function_call",
                    ),
                )

            async def second_stream():
                yield FakeEvent("response.output_text.delta", "Recovered")

            return first_stream() if call_index == 1 else second_stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response([], "Use a tool")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="missing_tool",
                tool_label="missing_tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="missing_tool",
                tool_label="missing_tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="failed",
                error="Unknown tool: missing_tool",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Recovered"),
    ]
    output = fake_client.responses.create_kwargs[1]["input"][-1]["output"]
    assert '"ok": false' in output
    assert "Unknown tool: missing_tool" in output


def test_registry_returns_same_room_for_same_chat_and_different_rooms_for_different_chats():
    async def run():
        registry = ChatRoomRegistry()
        chat_id = uuid4()

        first = await registry.get_room(chat_id)
        second = await registry.get_room(chat_id)
        other = await registry.get_room(uuid4())

        assert first is second
        assert first is not other

    asyncio.run(run())


def test_registry_releases_idle_room_after_stream_subscription_exits():
    async def run():
        registry = ChatRoomRegistry()
        chat_id = uuid4()
        room = await registry.get_room(chat_id)
        subscription = room.subscribe()
        subscription_task = asyncio.create_task(anext(subscription))
        await asyncio.sleep(0)

        await registry.release_room_if_idle(chat_id)
        assert chat_id in registry._rooms

        subscription_task.cancel()
        try:
            await subscription_task
        except asyncio.CancelledError:
            pass

        await registry.release_room_if_idle(chat_id)

        assert chat_id not in registry._rooms

    asyncio.run(run())


def test_stale_streaming_messages_are_marked_interrupted(monkeypatch):
    install_fake_session(monkeypatch)
    _, message = make_chat_and_message()

    asyncio.run(mark_stale_streaming_messages_interrupted(FakeAsyncSession()))

    assert message.status == MESSAGE_STATUS_INTERRUPTED
    assert FakeAsyncSession.commit_count == 1
