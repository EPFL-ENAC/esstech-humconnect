<template>
    <ChatActivityBlock
        :title="t('chat.activities.thinking')"
        :summary="summary"
        icon="psychology"
        color="#667085"
        mode="raw-only"
    >
        <template #raw>
            <div class="reasoning-text">{{ chunk.content }}</div>
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ChatMessageChunk } from 'src/utils/model';
import ChatActivityBlock from './ChatActivityBlock.vue';

const props = defineProps<{
    chunk: ChatMessageChunk;
}>();

const { t } = useI18n();
const characterCount = computed(() => Array.from(props.chunk.content).length);
const summary = computed(() => t('chat.activities.character', characterCount.value));
</script>

<style scoped lang="scss">
.reasoning-text {
    white-space: pre-wrap;
    word-break: break-word;
}
</style>
