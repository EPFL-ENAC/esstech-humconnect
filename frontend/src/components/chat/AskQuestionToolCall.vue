<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="help_outline"
        :color="toolColor"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ChatMarkdownContent
                v-if="!isActiveQuestion"
                class="ask-question-text"
                :content="payload.arguments.question"
            />
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import type { ComputedRef } from 'vue';
import { computed, inject } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatMarkdownContent from './ChatMarkdownContent.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import type { AskQuestionToolCallPayload } from './toolCallSchemas';

const toolColor = '#2563EB';

const props = defineProps<{
    payload: AskQuestionToolCallPayload;
}>();

const { t } = useI18n();
const activeQuestionCallId = inject<ComputedRef<string | null>>('activeQuestionCallId');

const isActiveQuestion = computed(() => activeQuestionCallId?.value === props.payload.call_id);

const mode = computed(() => (props.payload.status === 'failed' ? 'raw-only' : 'visual-and-raw'));

const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.status.running');
    }
    if (props.payload.status === 'failed') {
        return t('chat.activities.status.failed');
    }
    if (isActiveQuestion.value) {
        return t('chat.activities.askQuestion.waiting');
    }
    return t('chat.activities.askQuestion.answered');
});
</script>

<style scoped lang="scss">
.ask-question-text {
    min-width: 0;
}
</style>
