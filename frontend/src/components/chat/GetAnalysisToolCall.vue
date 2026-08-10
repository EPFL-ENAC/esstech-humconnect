<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="insights"
        :color="toolColor"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <RootCauseAnalysisTimeline
                :analysis="analysis"
                :loading="payload.status === 'running'"
                :accent-color="toolColor"
            />
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import RootCauseAnalysisTimeline from './RootCauseAnalysisTimeline.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import type { GetAnalysisToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: GetAnalysisToolCallPayload;
}>();

const toolColor = '#4e5ba6';
const { t } = useI18n();
const analysis = computed(() =>
    props.payload.status === 'finished' ? (props.payload.answer?.analysis ?? null) : null,
);
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || analysis.value ? 'visual-and-raw' : 'raw-only',
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.rootCauseAnalysis.loading');
    }

    if (analysis.value) {
        return analysis.value.status === 'completed'
            ? t('chat.activities.rootCauseAnalysis.completedSummary', analysis.value.current_level)
            : t(
                  'chat.activities.rootCauseAnalysis.inProgressSummary',
                  analysis.value.current_level,
              );
    }

    return t(`chat.activities.status.${props.payload.status}`);
});
</script>
