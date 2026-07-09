from tests.chat_room_helpers import *  # noqa: F403


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
