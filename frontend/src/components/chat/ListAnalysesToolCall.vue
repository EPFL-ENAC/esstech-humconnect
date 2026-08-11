<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="format_list_bulleted"
        :color="toolColor"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <div v-if="analyses" class="analysis-list">
                <div v-if="!analyses.length" class="analysis-empty">
                    <q-icon name="inbox" size="22px" />
                    <span>{{ t('chat.activities.rootCauseAnalysis.noAnalyses') }}</span>
                </div>
                <div v-for="analysis in analyses" :key="analysis.analysis_id" class="analysis-row">
                    <span class="status-dot" :class="`status-dot--${analysis.status}`" />
                    <div class="analysis-row-main">
                        <p class="analysis-row-title">{{ analysis.problem_statement }}</p>
                        <div class="analysis-row-meta">
                            <span class="status-badge" :class="`status-badge--${analysis.status}`">
                                {{
                                    t(
                                        `chat.activities.rootCauseAnalysis.statuses.${analysis.status}`,
                                    )
                                }}
                            </span>
                            <span class="level-chip">{{
                                t('chat.activities.rootCauseAnalysis.levelOf', {
                                    current: analysis.current_level,
                                    max: MAX_WHYS,
                                })
                            }}</span>
                        </div>
                    </div>
                </div>
            </div>
            <div v-else class="analysis-list-loading">
                <q-spinner-dots size="22px" />
            </div>
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
import ToolCallRawContent from './ToolCallRawContent.vue';
import type { ListAnalysesToolCallPayload } from './toolCallSchemas';

const MAX_WHYS = 5;

const props = defineProps<{
    payload: ListAnalysesToolCallPayload;
}>();

const toolColor = '#4e5ba6';
const { t } = useI18n();
const analyses = computed(() =>
    props.payload.status === 'finished' ? (props.payload.answer?.analyses ?? null) : null,
);
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || analyses.value ? 'visual-and-raw' : 'raw-only',
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.rootCauseAnalysis.listing');
    }

    if (analyses.value) {
        return t('chat.activities.rootCauseAnalysis.analysesCount', analyses.value.length);
    }

    return t(`chat.activities.status.${props.payload.status}`);
});
</script>

<style scoped lang="scss">
.analysis-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
}

.analysis-empty {
    align-items: center;
    background: #f8fafc;
    border: 1px dashed #d0d5dd;
    border-radius: 6px;
    color: #667085;
    display: flex;
    gap: 8px;
    justify-content: center;
    min-height: 64px;
    padding: 10px;
}

.analysis-row {
    align-items: flex-start;
    background: #f8fafc;
    border: 1px solid #eaecf0;
    border-radius: 8px;
    display: flex;
    gap: 10px;
    padding: 10px 12px;
}

.status-dot {
    border-radius: 50%;
    flex: 0 0 auto;
    height: 9px;
    margin-top: 5px;
    width: 9px;
}

.status-dot--in_progress {
    background: #f79009;
}

.status-dot--completed {
    background: #12b76a;
}

.analysis-row-main {
    min-width: 0;
}

.analysis-row-title {
    color: #344054;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
    margin: 0 0 6px;
    overflow-wrap: anywhere;
}

.analysis-row-meta {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.status-badge {
    border-radius: 5px;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.02em;
    padding: 2px 6px;
    text-transform: uppercase;
}

.status-badge--in_progress {
    background: #f79009;
}

.status-badge--completed {
    background: #12b76a;
}

.level-chip {
    background: #eaecf0;
    border-radius: 5px;
    color: #475467;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
}

.analysis-list-loading {
    align-items: center;
    color: #4e5ba6;
    display: flex;
    min-height: 48px;
}
</style>
