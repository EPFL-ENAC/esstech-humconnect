import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { createChat, listChats } from 'src/utils/chatApi';
import { getI18nT } from 'src/utils/i18n';
import type { ChatSession } from 'src/utils/model';

export const useChatsStore = defineStore('chats', () => {
    const t = getI18nT();
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
            chats.value = await listChats();
        } catch (err) {
            error.value = err instanceof Error ? err.message : t('errors.loadChats');
        } finally {
            loading.value = false;
        }
    }

    async function createNewChat() {
        creating.value = true;
        error.value = '';

        try {
            return await createChat();
        } catch (err) {
            error.value = err instanceof Error ? err.message : t('errors.createChat');
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
