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
            <div v-if="whyStep" class="why-step" :style="{ '--rca-accent': toolColor }">
                <span class="why-level-badge">{{
                    t('chat.activities.rootCauseAnalysis.whyLevel', { level: whyStep.level })
                }}</span>
                <div class="why-qa">
                    <p class="why-qa-line">
                        <span class="rca-tag rca-tag--q">{{
                            t('chat.activities.rootCauseAnalysis.questionTag')
                        }}</span>
                        <span class="why-qa-text">{{ whyStep.question }}</span>
                    </p>
                    <p class="why-qa-line">
                        <span class="rca-tag rca-tag--a">{{
                            t('chat.activities.rootCauseAnalysis.answerTag')
                        }}</span>
                        <span class="why-qa-text">{{ whyStep.answer }}</span>
                    </p>
                </div>
            </div>
            <div v-else class="why-step-loading">
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
import type { SaveWhyStepToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: SaveWhyStepToolCallPayload;
}>();

const toolColor = '#4e5ba6';
const { t } = useI18n();

interface WhyStep {
    level: number;
    question: string;
    answer: string;
}

const whyStep = computed<WhyStep | null>(() => {
    if (props.payload.status !== 'finished' || !props.payload.answer) {
        return null;
    }

    const level = props.payload.answer.analysis.current_level;
    if (level < 1) {
        return null;
    }

    return {
        level,
        question: props.payload.arguments.question,
        answer: props.payload.arguments.answer,
    };
});

const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || whyStep.value ? 'visual-and-raw' : 'raw-only',
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.rootCauseAnalysis.savingWhyStep');
    }

    if (whyStep.value) {
        return t('chat.activities.rootCauseAnalysis.savedWhyStep', { level: whyStep.value.level });
    }

    return t(`chat.activities.status.${props.payload.status}`);
});
</script>

<style scoped lang="scss">
.why-step {
    --rca-accent: #4e5ba6;
    min-width: 0;
}

.why-level-badge {
    background: var(--rca-accent);
    border-radius: 6px;
    color: #fff;
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    margin-bottom: 10px;
    padding: 3px 8px;
}

.why-qa {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.why-qa-line {
    align-items: flex-start;
    display: flex;
    gap: 8px;
    margin: 0;
}

.why-qa-text {
    color: #344054;
    font-size: 13px;
    line-height: 1.5;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}

.rca-tag {
    border-radius: 5px;
    color: #fff;
    flex: 0 0 auto;
    font-size: 10px;
    font-weight: 700;
    line-height: 1;
    margin-top: 3px;
    padding: 3px 5px;
}

.rca-tag--q {
    background: var(--rca-accent);
}

.rca-tag--a {
    background: #475467;
}

.why-step-loading {
    align-items: center;
    color: var(--rca-accent, #4e5ba6);
    display: flex;
    min-height: 48px;
}
</style>
