import asyncio
import os
from uuid import uuid4

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")

from api.models.chat import ChatSession, Message
from api.services import chat as chat_service
from api.services.chat import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_ERROR,
    MESSAGE_STATUS_STREAMING,
    ChatStreamManager,
)


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

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.local_commit_count += 1
        self.__class__.commit_count += 1

    @classmethod
    def reset(cls):
        cls.commit_count = 0
        cls.instances = []
        cls.rows = {
            ChatSession: {},
            Message: {},
        }


async def immediate_sleep(delay):
    return None


def capture_broadcast(events):
    async def broadcast(chat_id, event):
        events.append(event)

    return broadcast


def install_fake_session(monkeypatch):
    FakeAsyncSession.reset()
    monkeypatch.setattr(chat_service, "AsyncSQLModelSession", FakeAsyncSession)
    monkeypatch.setattr(chat_service, "get_engine", lambda: object())
    monkeypatch.setattr(chat_service.asyncio, "sleep", immediate_sleep)


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


def test_placeholder_stream_broadcasts_deltas_and_commits_once_for_short_response(
    monkeypatch,
):
    install_fake_session(monkeypatch)
    monkeypatch.setattr(chat_service.random, "randint", lambda start, end: 42)
    manager = ChatStreamManager()
    events = []
    monkeypatch.setattr(manager, "broadcast", capture_broadcast(events))
    chat, message = make_chat_and_message()

    asyncio.run(manager._stream_placeholder_response(chat.id, message.id))

    response = "Random number: 42"
    assert [event["delta"] for event in events[:-1]] == list(response)
    assert events[-1] == {
        "type": "message_done",
        "message_id": str(message.id),
        "status": MESSAGE_STATUS_COMPLETE,
    }
    assert message.content == response
    assert message.status == MESSAGE_STATUS_COMPLETE
    assert chat.updated_at >= chat.created_at
    assert FakeAsyncSession.commit_count == 1


def test_placeholder_stream_batches_commits_for_longer_response(monkeypatch):
    install_fake_session(monkeypatch)
    monkeypatch.setattr(chat_service.random, "randint", lambda start, end: int("1" * 80))
    manager = ChatStreamManager()
    events = []
    monkeypatch.setattr(manager, "broadcast", capture_broadcast(events))
    chat, message = make_chat_and_message()

    asyncio.run(manager._stream_placeholder_response(chat.id, message.id))

    response = f"Random number: {int('1' * 80)}"
    assert len([event for event in events if event["type"] == "message_delta"]) == len(
        response
    )
    assert message.content == response
    assert message.status == MESSAGE_STATUS_COMPLETE
    assert FakeAsyncSession.commit_count < len(response)
    assert FakeAsyncSession.commit_count == 3


def test_placeholder_stream_returns_without_done_event_when_message_is_missing(
    monkeypatch,
):
    install_fake_session(monkeypatch)
    monkeypatch.setattr(chat_service.random, "randint", lambda start, end: 42)
    manager = ChatStreamManager()
    events = []
    monkeypatch.setattr(manager, "broadcast", capture_broadcast(events))

    asyncio.run(manager._stream_placeholder_response(uuid4(), uuid4()))

    assert events == []
    assert FakeAsyncSession.commit_count == 0


def test_placeholder_stream_marks_message_error_when_streaming_fails(monkeypatch):
    install_fake_session(monkeypatch)
    monkeypatch.setattr(chat_service.random, "randint", lambda start, end: 42)
    manager = ChatStreamManager()
    events = []
    chat, message = make_chat_and_message()

    async def broadcast(chat_id, event):
        if event["type"] == "message_delta":
            raise RuntimeError("stream failed")
        events.append(event)

    monkeypatch.setattr(manager, "broadcast", broadcast)

    asyncio.run(manager._stream_placeholder_response(chat.id, message.id))

    assert message.status == MESSAGE_STATUS_ERROR
    assert events == [
        {
            "type": "message_done",
            "message_id": str(message.id),
            "status": MESSAGE_STATUS_ERROR,
        }
    ]
    assert FakeAsyncSession.commit_count == 1
