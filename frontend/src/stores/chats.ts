import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { createChat, listChats, type ChatSession } from 'src/utils/chatApi';
import { getClientId } from 'src/utils/clientId';

export const useChatsStore = defineStore('chats', () => {
    const chats = ref<ChatSession[]>([]);
    const creating = ref(false);
    const error = ref('');
    const loading = ref(true);

    const sortedChats = computed(() =>
        [...chats.value].sort(
            (first, second) =>
                new Date(second.updated_at).getTime() - new Date(first.updated_at).getTime(),
        ),
    );

    async function loadChats() {
        loading.value = true;
        error.value = '';

        try {
            chats.value = await listChats(getClientId());
        } catch (err) {
            error.value = err instanceof Error ? err.message : 'Could not load chats.';
        } finally {
            loading.value = false;
        }
    }

    async function createNewChat() {
        creating.value = true;
        error.value = '';

        try {
            return await createChat(getClientId());
        } catch (err) {
            error.value = err instanceof Error ? err.message : 'Could not create chat.';
            return null;
        } finally {
            creating.value = false;
        }
    }

    function upsertChat(chat: ChatSession) {
        const index = chats.value.findIndex((item) => item.id === chat.id);
        if (index === -1) {
            chats.value.push(chat);
        } else {
            chats.value[index] = chat;
        }
    }

    return {
        chats: sortedChats,
        creating,
        error,
        loading,
        createNewChat,
        loadChats,
        upsertChat,
    };
});
