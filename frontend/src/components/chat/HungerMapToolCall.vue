<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="sym_o_nutrition"
        :color="toolColor"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                :accent-color="toolColor"
                :query="visualizationQuery"
                :filters="visualizationFilters"
                :warnings="result?.warnings"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #results>
                    <HungerMapCountryChart
                        v-if="countryEstimate && result"
                        :estimate="countryEstimate"
                        :source-url="result.source_url"
                    />
                    <HungerMap v-else-if="result" :response="result" />
                </template>
            </ToolCallVisualizationSkeleton>
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { HungerMapToolCallPayload } from './toolCallSchemas';

const HungerMap = defineAsyncComponent(() => import('./HungerMap.vue'));
const HungerMapCountryChart = defineAsyncComponent(() => import('./HungerMapCountryChart.vue'));

const props = defineProps<{
    payload: HungerMapToolCallPayload;
}>();

const toolColor = '#007dbc';
const { t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const countryEstimate = computed(() => {
    if (result.value?.scope !== 'country' || result.value.countries.length !== 1) {
        return null;
    }

    return result.value.countries[0] ?? null;
});
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() => ({
    icon: 'public',
    label: t('chat.activities.hungerMap.location'),
    value:
        props.payload.arguments.country === 'global'
            ? t('chat.activities.hungerMap.global')
            : props.payload.arguments.country,
}));
const visualizationFilters = computed(() => [
    {
        icon: 'sym_o_nutrition',
        label: t('chat.activities.hungerMap.indicator'),
        value: countryEstimate.value
            ? t('chat.activities.hungerMap.ipcBreakdown')
            : t('chat.activities.hungerMap.phaseThreePercentage'),
    },
]);
const visualizationResultsSummary = computed(() =>
    result.value
        ? t('chat.activities.hungerMap.areaEstimateCount', result.value.countries.length)
        : undefined,
);
const visualizationEmptyState = computed(() =>
    result.value && !result.value.countries.length && !result.value.headline
        ? {
              icon: 'public_off',
              message: t('chat.activities.hungerMap.noEstimates'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return props.payload.arguments.country === 'global'
            ? t('chat.activities.hungerMap.loadingGlobal')
            : t('chat.activities.hungerMap.loadingCountry', {
                  country: props.payload.arguments.country,
              });
    }

    if (result.value) {
        return t('chat.activities.hungerMap.result', result.value.countries.length);
    }

    return t(`chat.activities.status.${props.payload.status}`);
});
</script>
