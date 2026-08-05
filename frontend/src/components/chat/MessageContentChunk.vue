<template>
    <div class="q-my-md">
        <ChatMarkdownContent :content="chunk.content" />
    </div>
</template>

<script setup lang="ts">
import type { ChatMessageChunk, ChatMessageStatus } from 'src/utils/model';
import ChatMarkdownContent from './ChatMarkdownContent.vue';

defineProps<{
    chunk: ChatMessageChunk;
    status: ChatMessageStatus;
}>();
</script>
