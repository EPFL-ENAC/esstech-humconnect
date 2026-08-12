<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="volunteer_activism"
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
                    <ChatCardGallery v-if="result?.activities.length">
                        <ToolCardItem
                            v-for="activity in result.activities"
                            :key="activity.activity_id"
                            :href="activity.source_url"
                            :color="toolColor"
                            :eyebrow="reportingOrganisation(activity)"
                            :title="activity.title"
                            :extra-info="activityExtraInfo(activity)"
                        >
                            <template #content>
                                <p v-if="activity.description" class="activity-description">
                                    {{ activity.description }}
                                </p>
                                <p v-else class="activity-description activity-description-empty">
                                    {{ t('chat.activities.iati.noDescription') }}
                                </p>
                                <div
                                    v-if="
                                        activity.commitment_usd !== null ||
                                        activity.spend_usd !== null
                                    "
                                    class="finance-labels"
                                >
                                    <q-badge
                                        v-if="activity.commitment_usd !== null"
                                        outline
                                        color="deep-purple-7"
                                    >
                                        {{ t('chat.activities.iati.commitment') }}
                                        {{ formatUsd(activity.commitment_usd) }}
                                    </q-badge>
                                    <q-badge
                                        v-if="activity.spend_usd !== null"
                                        outline
                                        color="teal-7"
                                    >
                                        {{ t('chat.activities.iati.spend') }}
                                        {{ formatUsd(activity.spend_usd) }}
                                    </q-badge>
                                </div>
                            </template>
                        </ToolCardItem>
                    </ChatCardGallery>
                </template>
            </ToolCallVisualizationSkeleton>
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import ToolCardItem from './ToolCardItem.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { IatiActivitySearchToolCallPayload, IatiActivitySummary } from './toolCallSchemas';

const props = defineProps<{
    payload: IatiActivitySearchToolCallPayload;
}>();

const toolColor = '#6941c6';
const { t } = useI18n();
const { formatDateRange, formatNumber } = useLocalizedFormatters();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() =>
    props.payload.arguments.query
        ? {
              label: t('chat.activities.iati.query'),
              value: props.payload.arguments.query,
              icon: 'search',
          }
        : null,
);
const visualizationFilters = computed(() => {
    const arguments_ = props.payload.arguments;
    const filters: Array<{ icon: string; label: string; value: string }> = [];

    addListFilter(filters, 'public', 'countries', arguments_.country_codes);
    addListFilter(filters, 'category', 'sectors', arguments_.sector_codes);
    addListFilter(filters, 'account_tree', 'sectorGroups', arguments_.sector_group_codes);
    addListFilter(
        filters,
        'corporate_fare',
        'reportingOrganisations',
        arguments_.reporting_organisation_refs,
    );
    if (arguments_.humanitarian !== null) {
        filters.push({
            icon: 'emergency',
            label: t('chat.activities.iati.humanitarian'),
            value: arguments_.humanitarian
                ? t('chat.activities.iati.yes')
                : t('chat.activities.iati.no'),
        });
    }
    if (arguments_.active_from_year !== null || arguments_.active_to_year !== null) {
        filters.push({
            icon: 'date_range',
            label: t('chat.activities.iati.activePeriod'),
            value: formatYearRange(arguments_.active_from_year, arguments_.active_to_year),
        });
    }

    return filters;
});
const visualizationResultsSummary = computed(() => {
    if (!result.value) {
        return undefined;
    }

    return t('chat.activities.iati.resultSummary', {
        total: formatNumber(result.value.total),
        shown: formatNumber(result.value.returned),
    });
});
const visualizationEmptyState = computed(() =>
    result.value && !result.value.activities.length
        ? {
              icon: 'travel_explore',
              message: t('chat.activities.iati.noResults'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return props.payload.arguments.query
            ? t('chat.activities.iati.searchingQuery', {
                  query: props.payload.arguments.query,
              })
            : t('chat.activities.iati.searching');
    }

    if (result.value) {
        return t('chat.activities.iati.result', result.value.returned);
    }

    return t(`chat.activities.status.${props.payload.status}`);
});

function addListFilter(
    filters: Array<{ icon: string; label: string; value: string }>,
    icon: string,
    labelKey: string,
    values: string[],
): void {
    if (values.length) {
        filters.push({
            icon,
            label: t(`chat.activities.iati.${labelKey}`),
            value: values.join(' · '),
        });
    }
}

function formatYearRange(start: number | null, end: number | null): string {
    if (start !== null && end !== null) {
        return `${start}–${end}`;
    }
    if (start !== null) {
        return t('chat.activities.iati.fromYear', { year: start });
    }
    return t('chat.activities.iati.throughYear', { year: end });
}

function reportingOrganisation(activity: IatiActivitySummary): string {
    return (
        activity.reporting_organisation.name ??
        activity.reporting_organisation.reference ??
        t('chat.activities.iati.provider')
    );
}

function formatUsd(value: number): string {
    return formatNumber(value, {
        style: 'currency',
        currency: 'USD',
        notation: 'compact',
        maximumFractionDigits: 1,
    });
}

function activityExtraInfo(activity: IatiActivitySummary) {
    return [
        { icon: 'fingerprint', value: activity.activity_id },
        {
            icon: 'calendar_today',
            value: formatDateRange(
                activity.start_date,
                activity.end_date,
                t('chat.activities.iati.unknownDate'),
                { dateStyle: 'medium' },
            ),
        },
        {
            icon: 'info',
            value: activity.status ?? t('chat.activities.iati.unknownStatus'),
        },
    ];
}
</script>

<style scoped lang="scss">
.activity-description {
    color: #475467;
    display: -webkit-box;
    font-size: 12px;
    -webkit-line-clamp: 4;
    line-height: 1.45;
    margin: 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
}

.activity-description-empty {
    color: #98a2b3;
    font-style: italic;
}

.finance-labels {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
}
</style>
