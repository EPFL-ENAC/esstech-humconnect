import asyncio
import os
from uuid import uuid4

import pytest

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")

from api.models.chat import ChatMessageResponse, ChatSession, Message, utc_now
from api.services import chat as chat_service
from api.services.chat_room import chat_assistant as chat_assistant_module
from api.services.chat_room import chat_db as chat_db_module
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
        self.completed = False
        self.failed = False
        self.active = True
        self.active_response_message_id = None

    async def client_has_access(self, client_id):
        return client_id == "client-1"

    async def build_snapshot(self, client_id):
        return None

    async def get_assistant_chat_history(self):
        return list(self.chat_history)

    async def submit_question(self, client_id, question):
        self.created_turns.append((client_id, question))
        chat_id = uuid4()
        user_message = Message(
            chat_id=chat_id,
            role=MESSAGE_ROLE_USER,
            content=question,
            status=MESSAGE_STATUS_COMPLETE,
        )
        return ChatMessageResponse.from_db_model(user_message)

    async def response_progress(self, tokens):
        self.progress_tokens.append(tokens)
        if self.active_response_message_id is None:
            self.active_response_message_id = uuid4()
            created_at = utc_now()
            return ChatMessageResponse(
                id=self.active_response_message_id,
                chat_id=uuid4(),
                role=MESSAGE_ROLE_ASSISTANT,
                content=tokens,
                status=MESSAGE_STATUS_STREAMING,
                created_at=created_at,
                updated_at=created_at,
            )
        return None

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
            yield chunk


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
        content="",
        status=MESSAGE_STATUS_STREAMING,
    )
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    FakeAsyncSession.rows[Message][message.id] = message
    return chat, message


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
    first = Message(
        chat_id=chat.id,
        role=MESSAGE_ROLE_USER,
        content="First",
        status=MESSAGE_STATUS_COMPLETE,
    )
    second = Message(
        chat_id=chat.id,
        role=MESSAGE_ROLE_ASSISTANT,
        content="Second",
        status=MESSAGE_STATUS_COMPLETE,
    )
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    FakeAsyncSession.rows[Message][first.id] = first
    FakeAsyncSession.rows[Message][second.id] = second
    history = PersistentChatMessagesHistory(chat.id)

    snapshot = asyncio.run(history.build_snapshot("client-1"))

    assert snapshot is not None
    assert snapshot.chat.id == chat.id
    assert [message.content for message in snapshot.messages] == ["First", "Second"]


def test_persistent_history_submit_question_writes_user_and_caches_response(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    user_message = asyncio.run(history.submit_question("client-1", "Hello there"))

    snapshot = asyncio.run(history.build_snapshot("client-1"))
    assert user_message.role == MESSAGE_ROLE_USER
    assert snapshot is not None
    assert [message.content for message in snapshot.messages] == ["Hello there"]
    assert [
        row.role
        for row in FakeAsyncSession.instances[-1].added
        if isinstance(row, Message)
    ] == [MESSAGE_ROLE_USER]
    assert chat.title == "Hello there"
    assert FakeAsyncSession.commit_count == 1


def test_persistent_history_first_response_progress_creates_response_record(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        created_message = await history.response_progress("OK")
        snapshot = await history.build_snapshot("client-1")
        return created_message, snapshot

    created_message, snapshot = asyncio.run(run())

    assert created_message is not None
    persisted_message = FakeAsyncSession.rows[Message][created_message.id]
    assert persisted_message.content == "OK"
    assert persisted_message.status == MESSAGE_STATUS_STREAMING
    assert snapshot is not None
    assert snapshot.messages[-1].content == "OK"
    assert FakeAsyncSession.commit_count == 2


def test_persistent_history_response_progress_throttles_after_initial_insert(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        created_message = await history.response_progress("a")
        for _ in range(chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE - 1):
            await history.response_progress("a")

        snapshot = await history.build_snapshot("client-1")
        assert snapshot is not None
        assert snapshot.messages[-1].content == "a" * (
            chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE
        )
        assert FakeAsyncSession.commit_count == 2

        await history.response_progress("b")
        return created_message

    assistant_message = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.content == (
        "a" * chat_service.STREAM_COMMIT_TOKEN_BATCH_SIZE + "b"
    )
    assert FakeAsyncSession.commit_count == 3


def test_persistent_history_complete_response_flushes_and_marks_complete(monkeypatch):
    install_fake_session(monkeypatch)
    chat = ChatSession(client_id="client-1")
    FakeAsyncSession.rows[ChatSession][chat.id] = chat
    history = PersistentChatMessagesHistory(chat.id)

    asyncio.run(history.submit_question("client-1", "Hello"))

    async def run():
        assistant_message = await history.response_progress("OK")
        await history.complete_response()
        snapshot = await history.build_snapshot("client-1")
        return assistant_message, snapshot

    assistant_message, snapshot = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.content == "OK"
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

    async def run():
        assistant_message = await history.response_progress("Nope")
        await history.fail_response()
        snapshot = await history.build_snapshot("client-1")
        return assistant_message, snapshot

    assistant_message, snapshot = asyncio.run(run())

    assert assistant_message is not None
    persisted_message = FakeAsyncSession.rows[Message][assistant_message.id]
    assert persisted_message.content == "Nope"
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
        Message(
            chat_id=uuid4(),
            role=MESSAGE_ROLE_USER,
            content="Earlier question",
            status=MESSAGE_STATUS_COMPLETE,
        )
    )
    history.chat_history = [history_message]
    assistant = FakeAssistant(["O", "K"])
    room = ChatRoomService(
        uuid4(),
        messages_history=history,
        chat_assistant=assistant,
    )
    asyncio.run(
        room._stream_assistant_response(
            history.chat_history,
            "Latest question",
        )
    )

    assert assistant.calls == [([history_message], "Latest question")]
    assert history.progress_tokens == ["O", "K"]


def test_assistant_stream_pushes_every_chunk_and_broadcasts_deltas():
    history = FakeHistory()
    hub = ChatRoomConnectionHub()
    websocket = FakeWebSocket()
    assistant = FakeAssistant(["Hello", " ", "there"])
    room = ChatRoomService(
        uuid4(),
        connection_hub=hub,
        messages_history=history,
        chat_assistant=assistant,
    )
    async def run():
        await room.connect(websocket)
        await room._stream_assistant_response([], "Hello?")

    asyncio.run(run())

    chunks = ["Hello", " ", "there"]
    assert history.progress_tokens == chunks
    assert history.completed
    created_event = websocket.events[0]
    assert created_event["type"] == "message_created"
    assert created_event["message"]["role"] == MESSAGE_ROLE_ASSISTANT
    assert created_event["message"]["content"] == chunks[0]
    assert [event["delta"] for event in websocket.events[1:-1]] == chunks[1:]
    assert websocket.events[-1] == {
        "type": "message_done",
        "message_id": created_event["message"]["id"],
        "status": MESSAGE_STATUS_COMPLETE,
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
        await room._stream_assistant_response()

    asyncio.run(run())

    assert websocket.events == []
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
        await room._stream_assistant_response()

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
        await room._stream_assistant_response()

    with pytest.raises(RuntimeError, match="done broadcast failed"):
        asyncio.run(run())

    assert history.completed
    assert not history.failed
    assert len(websocket.events) == 1
    assert websocket.events[0]["type"] == "message_created"


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
        await room._stream_assistant_response([], "Hello?")

    asyncio.run(run())

    assert not history.failed
    assert websocket.events == []


def test_placeholder_chat_assistant_streams_random_number(monkeypatch):
    monkeypatch.setattr(chat_assistant_module.random, "randint", lambda start, end: 42)
    monkeypatch.setattr(chat_assistant_module.asyncio, "sleep", immediate_sleep)
    assistant = PlaceholderChatAssistant()

    async def run():
        return [
            token
            async for token in assistant.stream_response([], "What number?")
        ]

    assert asyncio.run(run()) == list("Random number: 42")


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
