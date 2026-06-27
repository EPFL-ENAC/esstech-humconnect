<template>
    <q-expansion-item
        dense
        switch-toggle-side
        class="tool-call"
        header-class="tool-call-header"
        icon="construction"
        :label="toolName"
        :caption="statusLabel"
    >
        <div class="tool-call-content">
            <template v-if="payload">
                <div class="tool-call-section">
                    <div class="tool-call-section-title">Arguments</div>
                    <pre class="tool-call-json">{{ formattedArguments }}</pre>
                </div>
                <div v-if="payload.answer" class="tool-call-section">
                    <div class="tool-call-section-title">Answer</div>
                    <div>{{ payload.answer }}</div>
                </div>
                <div v-else-if="payload.error" class="tool-call-section tool-call-error">
                    <div class="tool-call-section-title">Error</div>
                    <div>{{ payload.error }}</div>
                </div>
                <q-spinner-dots v-else size="18px" color="grey-7" />
            </template>
            <template v-else-if="legacyToolOutput">
                {{ legacyToolOutput }}
            </template>
            <q-spinner-dots v-else size="18px" color="grey-7" />
        </div>
    </q-expansion-item>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ChatMessageChunk } from 'src/utils/model';

const props = defineProps<{
    chunk: ChatMessageChunk;
}>();

const payload = computed(() => props.chunk.payload);

const firstLine = computed(() => props.chunk.content.split(/\r?\n/, 1)[0]?.trim() ?? '');

const toolName = computed(() => {
    if (payload.value) {
        return payload.value.tool_label;
    }

    const callingMatch = firstLine.value.match(/^Calling\s+(.+?)\.\.\.$/);
    if (callingMatch?.[1]) {
        return callingMatch[1];
    }

    const completionMatch = firstLine.value.match(/^(.+?)\s+(finished|failed)$/i);
    if (completionMatch?.[1]) {
        return completionMatch[1];
    }

    return firstLine.value || 'Tool call';
});

const legacyToolOutput = computed(() => {
    const firstNewlineIndex = props.chunk.content.search(/\r?\n/);
    if (firstNewlineIndex === -1) {
        return '';
    }

    return props.chunk.content.slice(firstNewlineIndex).trim();
});

const formattedArguments = computed(() => {
    if (!payload.value?.arguments) {
        return 'null';
    }

    return JSON.stringify(payload.value.arguments, null, 2);
});

const statusLabel = computed(() => {
    if (!payload.value) {
        return legacyToolOutput.value ? 'Finished' : 'Calling';
    }

    return {
        failed: 'Failed',
        finished: 'Finished',
        running: 'Running',
    }[payload.value.status];
});
</script>

<style scoped lang="scss">
.tool-call {
    border-left: 3px solid #667085;
    color: #475467;
    margin-bottom: 8px;
}

.tool-call :deep(.q-item) {
    min-height: 34px;
    padding: 0 6px;
}

.tool-call :deep(.q-item__section--avatar) {
    min-width: 24px;
    padding-right: 8px;
}

.tool-call :deep(.q-item__label) {
    font-size: 12px;
    font-weight: 600;
}

.tool-call :deep(.q-item__label--caption) {
    color: #667085;
    font-size: 11px;
    font-weight: 500;
}

.tool-call-content {
    font-size: 13px;
    line-height: 1.45;
    min-height: 24px;
    padding: 4px 8px 8px 54px;
    white-space: pre-wrap;
    word-break: break-word;
}

.tool-call-section + .tool-call-section {
    margin-top: 10px;
}

.tool-call-section-title {
    color: #667085;
    font-size: 11px;
    font-weight: 600;
    margin-bottom: 3px;
    text-transform: uppercase;
}

.tool-call-json {
    background: #f8fafc;
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-radius: 6px;
    font-size: 12px;
    margin: 0;
    overflow-x: auto;
    padding: 8px;
    white-space: pre;
}

.tool-call-error {
    color: #b42318;
}
</style>
