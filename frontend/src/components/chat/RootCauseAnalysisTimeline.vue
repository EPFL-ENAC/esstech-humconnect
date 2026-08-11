<template>
    <div class="rca-timeline" :style="{ '--rca-accent': accentColor }">
        <div v-if="loading && !analysis" class="rca-loading">
            <q-spinner-dots size="22px" />
        </div>

        <ol v-else-if="analysis" class="rca-steps">
            <li class="rca-step rca-step--problem">
                <span class="rca-dot"><q-icon name="flag" size="14px" /></span>
                <div class="rca-step-body">
                    <span class="rca-step-title">{{
                        t('chat.activities.rootCauseAnalysis.problem')
                    }}</span>
                    <p class="rca-step-text">{{ analysis.problem_statement }}</p>
                </div>
            </li>

            <li
                v-for="qa in analysis.questions_and_answers"
                :key="qa.level"
                class="rca-step rca-step--why"
            >
                <span class="rca-dot"><q-icon name="help_outline" size="14px" /></span>
                <div class="rca-step-body">
                    <span class="rca-step-title">{{
                        t('chat.activities.rootCauseAnalysis.whyLevel', { level: qa.level })
                    }}</span>
                    <div class="rca-qa">
                        <p class="rca-qa-line">
                            <span class="rca-tag rca-tag--q">{{
                                t('chat.activities.rootCauseAnalysis.questionTag')
                            }}</span>
                            <span class="rca-qa-text">{{ qa.question }}</span>
                        </p>
                        <p class="rca-qa-line">
                            <span class="rca-tag rca-tag--a">{{
                                t('chat.activities.rootCauseAnalysis.answerTag')
                            }}</span>
                            <span class="rca-qa-text">{{
                                qa.answer ?? t('chat.activities.rootCauseAnalysis.pendingAnswer')
                            }}</span>
                        </p>
                    </div>
                </div>
            </li>

            <li v-if="analysis.root_cause" class="rca-step rca-step--root">
                <span class="rca-dot rca-dot--root"><q-icon name="task_alt" size="14px" /></span>
                <div class="rca-step-body">
                    <span class="rca-step-title">{{
                        t('chat.activities.rootCauseAnalysis.rootCause')
                    }}</span>
                    <p class="rca-step-text">{{ analysis.root_cause }}</p>
                </div>
            </li>
        </ol>
    </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { RootCauseAnalysisSnapshot } from './toolCallSchemas';

defineProps<{
    analysis: RootCauseAnalysisSnapshot | null;
    loading?: boolean;
    accentColor?: string;
}>();

const { t } = useI18n();
</script>

<style scoped lang="scss">
.rca-timeline {
    --rca-accent: #4e5ba6;
    min-width: 0;
}

.rca-loading {
    align-items: center;
    color: var(--rca-accent);
    display: flex;
    min-height: 48px;
}

.rca-steps {
    list-style: none;
    margin: 0;
    padding: 0;
}

.rca-step {
    display: grid;
    grid-template-columns: 22px 1fr;
    gap: 10px;
    padding-bottom: 16px;
    position: relative;
}

.rca-step:last-child {
    padding-bottom: 0;
}

.rca-step:not(:last-child)::before {
    background: #eaecf0;
    bottom: 0;
    content: '';
    left: 10px;
    position: absolute;
    top: 26px;
    width: 2px;
}

.rca-dot {
    align-items: center;
    background: var(--rca-accent);
    border-radius: 50%;
    color: #fff;
    display: flex;
    height: 22px;
    justify-content: center;
    margin-top: 2px;
    position: relative;
    width: 22px;
    z-index: 1;
}

.rca-dot--root {
    background: #12b76a;
}

.rca-step-body {
    min-width: 0;
}

.rca-step-title {
    color: #475467;
    display: block;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-bottom: 3px;
    text-transform: uppercase;
}

.rca-step--root .rca-step-title {
    color: #027a48;
}

.rca-step-text {
    color: #344054;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}

.rca-qa {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.rca-qa-line {
    align-items: flex-start;
    display: flex;
    gap: 8px;
    margin: 0;
}

.rca-qa-text {
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
</style>
