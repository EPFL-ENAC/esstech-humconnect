from tests.chat_room_helpers import *  # noqa: F403


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


def test_stale_streaming_messages_are_marked_interrupted(monkeypatch):
    install_fake_session(monkeypatch)
    _, message = make_chat_and_message()

    asyncio.run(mark_stale_streaming_messages_interrupted(FakeAsyncSession()))

    assert message.status == MESSAGE_STATUS_INTERRUPTED
    assert FakeAsyncSession.commit_count == 1
