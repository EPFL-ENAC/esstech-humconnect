<template>
    <component :is="resolvedToolCall.component" :payload="resolvedToolCall.payload" />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ChatMessageChunk } from 'src/utils/model';
import { resolveToolCall } from './toolCallRegistry';

const props = defineProps<{
    chunk: ChatMessageChunk;
}>();

const resolvedToolCall = computed(() => resolveToolCall(props.chunk.payload ?? null));
</script>
