import asyncio
import os
from uuid import uuid4

import pytest
from openai.types.responses import ResponseFunctionToolCall

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")

from api.models.chat import (
    CHUNK_TYPE_MESSAGE_CONTENT,
    CHUNK_TYPE_REASONING_TEXT,
    CHUNK_TYPE_TOOL_CALL,
    ChatMessageChunk,
    ChatMessageResponse,
    ChatSession,
    Message,
    ToolCallPayload,
    utc_now,
)
from api.services import chat as chat_service
from api.services.chat_room import chat_assistant as chat_assistant_module
from api.services.chat_room import chat_db as chat_db_module
from api.services.chat_room import humconnect_assistant as humconnect_assistant_module
from api.services.chat_room.tools import events as events_tool_module
from api.services.chat_room.tools import meditron as meditron_tool_module
from api.services.chat_room.chat_assistant import (
    AssistantStreamChunkDelta,
    AssistantStreamPayloadUpdate,
)
from api.services.chat_room.tools import (
    ASK_MEDITRON_TOOL,
    RECORD_EVENT_TOOL,
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
    ChatRoomConnectionHub,
    ChatRoomRegistry,
    ChatRoomService,
    HumConnectAssistant,
    PersistentChatMessagesHistory,
    PlaceholderChatAssistant,
    mark_stale_streaming_messages_interrupted,
)


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
    rows = {
        ChatSession: {},
        Message: {},
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
        query_text = str(query)
        if "chatsession" in query_text:
            return FakeResult(list(self.rows[ChatSession].values()))

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

    async def commit(self):
        self.local_commit_count += 1
        self.__class__.commit_count += 1

    async def refresh(self, row):
        return None

    @classmethod
    def reset(cls):
        cls.commit_count = 0
        cls.instances = []
        cls.rows = {
            ChatSession: {},
            Message: {},
        }


class FakeWebSocket:
    def __init__(self, *, fail_send=False):
        self.accepted = False
        self.events = []
        self.fail_send = fail_send

    async def accept(self):
        self.accepted = True

    async def send_json(self, event):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.events.append(event)


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

    async def client_has_access(self, client_id):
        return client_id == "client-1"

    async def build_snapshot(self, client_id):
        return None

    async def get_assistant_chat_history(self):
        return list(self.chat_history)

    async def submit_question(self, client_id, question):
        self.created_turns.append((client_id, question))
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

    async def stream_response(self, chat_history, question):
        self.calls.append((list(chat_history), question))
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


async def immediate_sleep(delay):
    return None


def install_fake_session(monkeypatch):
    FakeAsyncSession.reset()
    monkeypatch.setattr(chat_db_module, "AsyncSQLModelSession", FakeAsyncSession)
    monkeypatch.setattr(chat_db_module, "get_engine", lambda: object())


def make_chat_and_message():
    chat = ChatSession(client_id="client-1")
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


def test_connection_hub_broadcasts_only_to_connected_sockets():
    async def run():
        first_hub = ChatRoomConnectionHub()
        second_hub = ChatRoomConnectionHub()
        first_socket = FakeWebSocket()
        second_socket = FakeWebSocket()

        await first_hub.connect(first_socket)
        await second_hub.connect(second_socket)
        await first_hub.broadcast({"type": "event"})

        assert first_socket.accepted
        assert first_socket.events == [{"type": "event"}]
        assert second_socket.events == []

    asyncio.run(run())


def test_connection_hub_removes_failed_sockets():
    async def run():
        hub = ChatRoomConnectionHub()
        websocket = FakeWebSocket(fail_send=True)

        await hub.connect(websocket)
        await hub.broadcast({"type": "event"})

        assert await hub.is_empty()

    asyncio.run(run())


def test_persistent_history_loads_messages_for_snapshot(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(client_id="client-1")
    first = make_db_message(chat.id, MESSAGE_ROLE_USER, "First", MESSAGE_STATUS_COMPLETE)
    second = make_db_message(
        chat.id, MESSAGE_ROLE_ASSISTANT, "Second", MESSAGE_STATUS_COMPLETE
    )
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    FakeAsyncSession.rows[Message][first.id] = first
    FakeAsyncSession.rows[Message][second.id] = second
    history = PersistentChatMessagesHistory(chat.id)

    snapshot = asyncio.run(history.build_snapshot("client-1"))

    assert snapshot is not None
    assert snapshot.chat.id == chat.id
    assert [message_content(message) for message in snapshot.messages] == [
        "First",
        "Second",
    ]


def test_persistent_history_submit_question_writes_user_and_caches_response(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    user_message = asyncio.run(history.submit_question("client-1", "Hello there"))

    snapshot = asyncio.run(history.build_snapshot("client-1"))
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
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        created_message = await history.start_response()
        snapshot = await history.build_snapshot("client-1")
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
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))
    chunk_index = 0

    async def run():
        assistant_message = await history.start_response()
        await history.response_progress(chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "a")
        for _ in range(chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE - 1):
            await history.response_progress(
                chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "a"
            )

        snapshot = await history.build_snapshot("client-1")
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
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)
    first_chunk_index = 0
    second_chunk_index = 1

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        await history.start_response()
        await history.response_progress(
            first_chunk_index, CHUNK_TYPE_REASONING_TEXT, "First"
        )
        await history.response_progress(
            second_chunk_index, CHUNK_TYPE_REASONING_TEXT, "Second"
        )
        snapshot = await history.build_snapshot("client-1")
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
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)
    payload = ToolCallPayload(
        tool_name="dummy_tool",
        tool_label="Dummy tool",
        call_id="call_1",
        arguments={"message": "hello"},
        status="running",
    )

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        assistant_message = await history.start_response()
        await history.response_payload_update(0, CHUNK_TYPE_TOOL_CALL, payload)
        snapshot = await history.build_snapshot("client-1")
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
    chat = ChatSession(client_id="client-1")
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

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        assistant_message = await history.start_response()
        await history.response_payload_update(0, CHUNK_TYPE_TOOL_CALL, running_payload)
        await history.response_payload_update(0, CHUNK_TYPE_TOOL_CALL, finished_payload)
        snapshot = await history.build_snapshot("client-1")
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
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))
    chunk_index = 0

    async def run():
        assistant_message = await history.start_response()
        await history.response_progress(chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "OK")
        await history.complete_response()
        snapshot = await history.build_snapshot("client-1")
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
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))
    chunk_index = 0

    async def run():
        assistant_message = await history.start_response()
        await history.response_progress(
            chunk_index, CHUNK_TYPE_MESSAGE_CONTENT, "Nope"
        )
        await history.fail_response()
        snapshot = await history.build_snapshot("client-1")
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
        hub = ChatRoomConnectionHub()
        websocket = FakeWebSocket()
        started_responses = []
        room = ChatRoomService(
            uuid4(),
            connection_hub=hub,
            messages_history=history,
        )

        async def start_assistant_response(chat_history, question):
            started_responses.append((chat_history, question))

        monkeypatch.setattr(
            room,
            "_start_assistant_response",
            start_assistant_response,
        )

        await room.connect(websocket)
        await room.handle_user_message("client-1", "Hello there")

        created_events = [
            event for event in websocket.events if event["type"] == "message_created"
        ]
        assert history.created_turns == [("client-1", "Hello there")]
        assert len(created_events) == 1
        assert created_events[0]["message"]["role"] == MESSAGE_ROLE_USER
        assert started_responses == [([], "Hello there")]

    asyncio.run(run())


def test_service_rejects_second_message_while_generation_is_active(monkeypatch):
    history = FakeHistory()
    room = ChatRoomService(uuid4(), messages_history=history)

    async def has_active_generation():
        return True

    monkeypatch.setattr(room, "has_active_generation", has_active_generation)

    with pytest.raises(RuntimeError, match="already streaming"):
        asyncio.run(room.handle_user_message("client-1", "Hello"))

    assert history.created_turns == []


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

    assert assistant.calls == [([history_message], "Latest question")]
    assert history.progress_tokens == [
        (0, CHUNK_TYPE_MESSAGE_CONTENT, "O"),
        (0, CHUNK_TYPE_MESSAGE_CONTENT, "K"),
    ]


def test_assistant_stream_pushes_every_chunk_and_broadcasts_deltas():
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
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
        connection_hub=hub,
        messages_history=history,
        chat_assistant=assistant,
    )
    async def run():
        await room.connect(websocket)
        await start_and_wait_for_response(room, [], "Hello?")

    asyncio.run(run())

    chunks = [
        (0, CHUNK_TYPE_REASONING_TEXT, "Thinking"),
        (1, CHUNK_TYPE_MESSAGE_CONTENT, "Hello"),
        (1, CHUNK_TYPE_MESSAGE_CONTENT, " there"),
    ]
    assert history.progress_tokens == chunks
    assert history.completed
    created_event = websocket.events[0]
    assert created_event["type"] == "message_created"
    assert created_event["message"]["role"] == MESSAGE_ROLE_ASSISTANT
    assert created_event["message"]["chunks"] == []
    assert websocket.events[1]["chunk_type"] == CHUNK_TYPE_REASONING_TEXT
    assert websocket.events[1]["chunk_index"] == 0
    assert websocket.events[1]["delta"] == "Thinking"
    assert websocket.events[2]["chunk_type"] == CHUNK_TYPE_MESSAGE_CONTENT
    assert websocket.events[2]["chunk_index"] == 1
    assert websocket.events[2]["delta"] == "Hello"
    assert websocket.events[3]["chunk_type"] == CHUNK_TYPE_MESSAGE_CONTENT
    assert websocket.events[3]["chunk_index"] == websocket.events[2]["chunk_index"]
    assert websocket.events[3]["delta"] == " there"
    assert websocket.events[-1] == {
        "type": "message_done",
        "message_id": created_event["message"]["id"],
        "status": MESSAGE_STATUS_COMPLETE,
    }


def test_assistant_stream_broadcasts_payload_updates():
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
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
        connection_hub=hub,
        messages_history=history,
        chat_assistant=assistant,
    )

    async def run():
        await room.connect(websocket)
        await start_and_wait_for_response(room, [], "Hello?")

    asyncio.run(run())

    created_event = websocket.events[0]
    assert history.payload_updates == [(0, CHUNK_TYPE_TOOL_CALL, payload)]
    assert websocket.events[1] == {
        "type": "message_update_payload",
        "message_id": created_event["message"]["id"],
        "chunk_index": 0,
        "chunk_type": CHUNK_TYPE_TOOL_CALL,
        "payload": payload.model_dump(mode="json"),
    }


def test_assistant_stream_returns_without_done_event_when_no_tokens_are_generated():
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
    assistant = FakeAssistant([])
    room = ChatRoomService(
        uuid4(),
        connection_hub=hub,
        messages_history=history,
        chat_assistant=assistant,
    )

    async def run():
        await room.connect(websocket)
        await start_and_wait_for_response(room)

    asyncio.run(run())

    assert websocket.events[0]["type"] == "message_created"
    assert websocket.events[0]["message"]["chunks"] == []
    assert websocket.events[1] == {
        "type": "message_done",
        "message_id": websocket.events[0]["message"]["id"],
        "status": MESSAGE_STATUS_COMPLETE,
    }
    assert history.progress_tokens == []
    assert assistant.calls == [([], "")]


def test_assistant_stream_marks_message_error_when_streaming_fails(monkeypatch):
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
    room = ChatRoomService(
        uuid4(),
        connection_hub=hub,
        messages_history=history,
        chat_assistant=FakeAssistant(["created", "broken"]),
    )

    async def broadcast(event):
        if event["type"] == "message_delta":
            raise RuntimeError("stream failed")
        await hub.broadcast(event)

    monkeypatch.setattr(room, "broadcast", broadcast)

    async def run():
        await room.connect(websocket)
        await start_and_wait_for_response(room)

    asyncio.run(run())

    assert history.failed
    assert websocket.events[0]["type"] == "message_created"
    assert websocket.events[1] == {
        "type": "message_done",
        "message_id": websocket.events[0]["message"]["id"],
        "status": MESSAGE_STATUS_ERROR,
    }


def test_assistant_stream_does_not_mark_error_when_done_broadcast_fails(monkeypatch):
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
    room = ChatRoomService(
        uuid4(),
        connection_hub=hub,
        messages_history=history,
        chat_assistant=FakeAssistant(["done"]),
    )

    async def broadcast(event):
        if event["type"] == "message_done":
            raise RuntimeError("done broadcast failed")
        await hub.broadcast(event)

    monkeypatch.setattr(room, "broadcast", broadcast)

    async def run():
        await room.connect(websocket)
        await start_and_wait_for_response(room)

    with pytest.raises(RuntimeError, match="done broadcast failed"):
        asyncio.run(run())

    assert history.completed
    assert not history.failed
    assert len(websocket.events) == 2
    assert websocket.events[0]["type"] == "message_created"
    assert websocket.events[1]["type"] == "message_delta"


def test_assistant_stream_marks_message_error_when_assistant_fails():
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
    room = ChatRoomService(
        uuid4(),
        connection_hub=hub,
        messages_history=history,
        chat_assistant=FakeAssistant([RuntimeError("assistant failed")]),
    )

    async def run():
        await room.connect(websocket)
        await start_and_wait_for_response(room, [], "Hello?")

    asyncio.run(run())

    assert history.failed
    assert websocket.events[0]["type"] == "message_created"
    assert websocket.events[0]["message"]["chunks"] == []
    assert websocket.events[1] == {
        "type": "message_done",
        "message_id": websocket.events[0]["message"]["id"],
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


def test_record_event_tool_appends_event_to_memory():
    events_tool_module.RECORDED_EVENTS.clear()

    async def run():
        return await RECORD_EVENT_TOOL.execute(
            {"event": "I have 3 kids that cough since yesterday"}
        )

    assert asyncio.run(run()) == (
        "Recorded event #1: I have 3 kids that cough since yesterday"
    )
    assert events_tool_module.RECORDED_EVENTS == [
        "I have 3 kids that cough since yesterday"
    ]


@pytest.mark.parametrize("event", ["", 123, None])
def test_record_event_tool_rejects_missing_or_empty_event(event):
    async def run():
        return await RECORD_EVENT_TOOL.execute({"event": event})

    with pytest.raises(ValueError, match="non-empty string event"):
        asyncio.run(run())


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
    events_tool_module.RECORDED_EVENTS.clear()

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
                            '{"event": "I have 3 kids that cough since yesterday"}'
                        ),
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
            async for chunk in assistant.stream_response([], "Remember this")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="record_event",
                tool_label="Record event",
                call_id="call_record_event",
                arguments={"event": "I have 3 kids that cough since yesterday"},
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
                arguments={"event": "I have 3 kids that cough since yesterday"},
                status="finished",
                answer=(
                    "Recorded event #1: "
                    "I have 3 kids that cough since yesterday"
                ),
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Noted"),
    ]
    assert events_tool_module.RECORDED_EVENTS == [
        "I have 3 kids that cough since yesterday"
    ]

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_record_event",
        "output": (
            '{"ok": true, "result": "Recorded event #1: '
            'I have 3 kids that cough since yesterday"}'
        ),
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


def test_registry_releases_idle_room_after_disconnect():
    async def run():
        registry = ChatRoomRegistry()
        chat_id = uuid4()
        room = await registry.get_room(chat_id)
        websocket = FakeWebSocket()

        await room.connect(websocket)
        await room.disconnect(websocket)
        await registry.release_room(chat_id)

        assert chat_id not in registry._rooms

    asyncio.run(run())


def test_stale_streaming_messages_are_marked_interrupted(monkeypatch):
    install_fake_session(monkeypatch)
    _, message = make_chat_and_message()

    async def has_active_generation(chat_id):
        return False

    monkeypatch.setattr(
        chat_service.chat_room_registry,
        "has_active_generation",
        has_active_generation,
    )

    asyncio.run(mark_stale_streaming_messages_interrupted(FakeAsyncSession()))

    assert message.status == MESSAGE_STATUS_INTERRUPTED
    assert FakeAsyncSession.commit_count == 1


def test_active_generation_is_not_marked_interrupted(monkeypatch):
    install_fake_session(monkeypatch)
    _, message = make_chat_and_message()

    async def has_active_generation(chat_id):
        return True

    monkeypatch.setattr(
        chat_service.chat_room_registry,
        "has_active_generation",
        has_active_generation,
    )

    asyncio.run(mark_stale_streaming_messages_interrupted(FakeAsyncSession()))

    assert message.status == MESSAGE_STATUS_STREAMING
    assert FakeAsyncSession.commit_count == 0
