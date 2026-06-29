<template>
    <q-markdown class="message-text" :src="props.chunk.content" no-heading-anchor-links />
</template>

<script setup lang="ts">
import type { ChatMessageChunk, ChatMessageStatus } from 'src/utils/model';

const props = defineProps<{
    chunk: ChatMessageChunk;
    status: ChatMessageStatus;
}>();
</script>

<style scoped lang="scss">
.message-text {
    word-break: break-word;

    :deep(p) {
        margin: 0 0 0.75em;
    }

    :deep(p:last-child),
    :deep(ul:last-child),
    :deep(ol:last-child),
    :deep(pre:last-child),
    :deep(blockquote:last-child) {
        margin-bottom: 0;
    }

    :deep(ul),
    :deep(ol) {
        margin: 0.5em 0 0.75em;
        padding-left: 1.4em;
    }

    :deep(li + li) {
        margin-top: 0.25em;
    }

    :deep(pre) {
        overflow-x: auto;
        white-space: pre;
    }

    :deep(code) {
        white-space: break-spaces;
    }

    :deep(pre code) {
        white-space: pre;
    }

    // QMarkdown 3.0.0-rc.2 emits q-markup--line-number, while its CSS targets
    // q-markdown--line-number. Keep this local until the upstream class is fixed.
    :deep(.q-markup--line-number) {
        color: #9e9e9e;
        margin: 0;
        position: relative;
        text-align: left;
        white-space: pre;
        word-spacing: normal;
        word-break: normal;
        word-wrap: normal;
        line-height: 1.5;
        tab-size: 4;
        hyphens: none;
    }
}
</style>
