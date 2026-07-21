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
    ChatSession,
    ChatSessionResponse,
    ChatSnapshotResponse,
    Message,
    ToolCallPayload,
)
from api.models.recorded_event import (
    EVENT_CONTINENTS,
    EVENT_TAGS,
    EventLocation,
    RecordedEvent,
    RecordedEventResponse,
)
from api.models.user_profile import (
    PROFESSION_CATEGORIES,
    UserProfile,
    UserProfilePromptContext,
)
from api.services import chat as chat_service
from api.services import recorded_events as recorded_events_module
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
from api.services.chat_room import chat_assistant as chat_assistant_module
from api.services.chat_room import chat_db as chat_db_module
from api.services.chat_room import humconnect_assistant as humconnect_assistant_module
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
    ToolCallInputItem,
    ToolCallOutput,
    ToolExecutionContext,
)
from api.services.chat_room.tools import events as events_tool_module
from api.services.chat_room.tools import (
    humanitarian_context as humanitarian_context_tool_module,
)
from api.services.chat_room.tools import meditron as meditron_tool_module
from api.services.chat_room.tools import natural_events as natural_events_tool_module
from api.services.reliefweb import client as reliefweb_client_module
from api.utils.datetime_utils import utc_now

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

    async def build_snapshot(self, user_id, *, interrupt_stale_streaming_messages=True):
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


class FakeOpenAIStreamEvent:
    def __init__(self, event_type, delta="", item=None):
        self.type = event_type
        self.delta = delta
        self.item = item


class FakeOpenAIResponses:
    def __init__(self, streams):
        self.streams = streams
        self.create_kwargs = []

    async def create(self, **kwargs):
        self.create_kwargs.append(kwargs)
        stream_events = self.streams[len(self.create_kwargs) - 1]

        async def stream():
            for event in stream_events:
                yield event

        return stream()


class FakeOpenAIClient:
    def __init__(self, streams):
        self.responses = FakeOpenAIResponses(streams)


def install_fake_openai_client(monkeypatch, streams):
    fake_client = FakeOpenAIClient(streams)
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    return fake_client


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
    return "".join(
        chunk.content for chunk in message.chunks if chunk.type == chunk_type
    )


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


class FakeReliefWebResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


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
        "event_location": {
            "raw_text": None,
            "continent": None,
            "country_code": None,
            "region": None,
            "city": None,
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": None,
        },
        "tags": ["health_incident"],
        "keywords": ["symptom", "cough"],
        "affected_profession_categories": ["medical_clinical"],
        "response_profession_categories": ["medical_clinical"],
        "severity": {"local": 7.5, "country": 4.0, "global": 1.5},
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
            "event": RecordedEventResponse.from_recorded_event(event).model_dump(
                mode="json"
            ),
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
    keywords=None,
    affected_profession_categories=None,
    response_profession_categories=None,
    local_severity=7.5,
    country_severity=4.0,
    global_severity=1.5,
    created_at=datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
) -> RecordedEvent:
    location = EventLocation.model_validate(
        event_location
        or {
            "raw_text": None,
            "continent": None,
            "country_code": None,
            "region": None,
            "city": None,
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": None,
        }
    )
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
        location_raw_text=location.raw_text,
        location_continent=location.continent,
        location_country_code=location.country_code,
        location_region=location.region,
        location_city=location.city,
        location_address=location.address,
        location_place_name=location.place_name,
        location_detail=location.detail,
        location_latitude=(
            location.coordinates.latitude if location.coordinates is not None else None
        ),
        location_longitude=(
            location.coordinates.longitude if location.coordinates is not None else None
        ),
        tags=tags if tags is not None else ["health_incident"],
        keywords=keywords if keywords is not None else ["symptom", "cough"],
        affected_profession_categories=(
            affected_profession_categories
            if affected_profession_categories is not None
            else ["medical_clinical"]
        ),
        response_profession_categories=(
            response_profession_categories
            if response_profession_categories is not None
            else ["medical_clinical"]
        ),
        local_severity=local_severity,
        country_severity=country_severity,
        global_severity=global_severity,
        created_at=created_at,
    )


def expected_recall_events_tool_output(events: list[RecordedEvent]) -> str:
    return json.dumps(
        {
            "message": f"Recalled {len(events)} event(s).",
            "events": [
                RecordedEventResponse.from_recorded_event(event).model_dump(mode="json")
                for event in events
            ],
        },
        indent=2,
    )
