<template>
    <q-expansion-item
        dense
        switch-toggle-side
        class="reasoning"
        header-class="reasoning-header"
        label="Thinking"
    >
        <div class="reasoning-text">
            {{ chunk.content }}
        </div>
    </q-expansion-item>
</template>

<script setup lang="ts">
import type { ChatMessageChunk } from 'src/utils/model';

defineProps<{
    chunk: ChatMessageChunk;
}>();
</script>

<style scoped lang="scss">
.reasoning {
    border-left: 3px solid #9aa4b2;
    color: #475467;
    margin-bottom: 8px;
}

.reasoning :deep(.q-item) {
    min-height: 30px;
    padding: 0 6px;
}

.reasoning :deep(.q-item__label) {
    font-size: 12px;
    font-weight: 600;
}

.reasoning-text {
    font-size: 13px;
    line-height: 1.45;
    padding: 4px 8px 8px 30px;
    white-space: pre-wrap;
    word-break: break-word;
}
</style>
