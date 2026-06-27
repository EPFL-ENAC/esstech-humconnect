<template>
    <q-page class="index-page">
        <section class="index-content">
            <div class="header-row">
                <div>
                    <h1>{{ t('chats.title') }}</h1>
                    <p>{{ t('chats.subtitle') }}</p>
                </div>

                <q-btn
                    color="primary"
                    icon="add"
                    :label="t('chats.newChat')"
                    :loading="creating"
                    @click="startNewChat"
                />
            </div>

            <q-banner v-if="error" class="bg-red-1 text-red-9 q-mb-md" rounded>
                {{ error }}
            </q-banner>

            <q-list bordered separator class="chat-list">
                <q-item v-if="loading">
                    <q-item-section>{{ t('chats.loading') }}</q-item-section>
                </q-item>

                <q-item v-else-if="chats.length === 0">
                    <q-item-section>{{ t('chats.empty') }}</q-item-section>
                </q-item>

                <template v-else>
                    <q-item
                        v-for="chat in chats"
                        :key="chat.id"
                        clickable
                        @click="openChat(chat.id)"
                    >
                        <q-item-section>
                            <q-item-label>{{ chat.title || t('chats.untitledChat') }}</q-item-label>
                            <q-item-label caption>{{ formatDate(chat.updated_at) }}</q-item-label>
                        </q-item-section>
                        <q-item-section side>
                            <q-icon name="chevron_right" />
                        </q-item-section>
                    </q-item>
                </template>
            </q-list>
        </section>
    </q-page>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useChatsStore } from 'src/stores/chats';

const router = useRouter();
const { locale, t } = useI18n();
const chatsStore = useChatsStore();
const { chats, creating, error, loading } = storeToRefs(chatsStore);

async function startNewChat() {
    const chatId = await chatsStore.createNewChat();
    if (chatId) {
        await router.push(`/chat/${chatId}`);
    }
}

function openChat(chatId: string) {
    void router.push(`/chat/${chatId}`);
}

function formatDate(value: string) {
    return new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}

onMounted(() => {
    void chatsStore.loadChats();
});
</script>

<style scoped lang="scss">
.index-page {
    padding: 32px;
}

.index-content {
    max-width: 860px;
}

.header-row {
    align-items: center;
    display: flex;
    gap: 24px;
    justify-content: space-between;
    margin-bottom: 24px;
}

h1 {
    font-size: 32px;
    line-height: 1.2;
    margin: 0 0 6px;
}

p {
    color: #667085;
    margin: 0;
}

.chat-list {
    background: white;
}

@media (max-width: 640px) {
    .index-page {
        padding: 20px;
    }

    .header-row {
        align-items: stretch;
        flex-direction: column;
    }
}
</style>
