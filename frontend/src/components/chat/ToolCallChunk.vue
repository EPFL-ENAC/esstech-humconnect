<template>
    <component
        :is="resolveToolCallComponent(chunk.payload?.tool_name)"
        :payload="chunk.payload ?? null"
    />
</template>

<script setup lang="ts">
import type { ChatMessageChunk } from 'src/utils/model';
import { resolveToolCallComponent } from './toolCallRegistry';

defineProps<{
    chunk: ChatMessageChunk;
}>();
</script>
