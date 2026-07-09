from tests.chat_room_helpers import *  # noqa: F403


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
