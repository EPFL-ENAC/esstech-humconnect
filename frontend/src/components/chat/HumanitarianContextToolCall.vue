<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="public"
        color="#1570ef"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                accent-color="#1570ef"
                :query="visualizationQuery"
                :filters="visualizationFilters"
                :warnings="result?.warnings"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #results>
                    <ChatCardGallery v-if="result?.items.length">
                        <ToolCardItem
                            v-for="item in result.items"
                            :key="`${item.type}-${item.id}`"
                            :href="item.source_url ?? undefined"
                            color="#1570ef"
                            :eyebrow="formatItemType(item.type)"
                            :title="item.title"
                            :extra-info="itemExtraInfo(item)"
                        >
                            <template #content>
                                <div class="item-category">{{ item.category }}</div>
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
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import ToolCardItem from './ToolCardItem.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type {
    HumanitarianContextItem,
    HumanitarianContextToolCallPayload,
} from './toolCallSchemas';

const props = defineProps<{
    payload: HumanitarianContextToolCallPayload;
}>();

const { locale, t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const country = computed(() => props.payload.arguments.country_name);
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() =>
    result.value
        ? {
              label: t('chat.activities.humanitarian.reportQuery'),
              value: result.value.filters.report_query,
          }
        : null,
);
const visualizationFilters = computed(() => {
    const filters = result.value?.filters;
    if (!filters) {
        return [];
    }

    return [
        {
            icon: 'public',
            label: t('chat.activities.humanitarian.country'),
            value: filters.country,
        },
        {
            icon: 'calendar_today',
            label: t('chat.activities.humanitarian.createdFrom'),
            value: formatDate(filters.created_from),
        },
        {
            icon: 'filter_list',
            label: t('chat.activities.humanitarian.limit'),
            value: t('chat.activities.humanitarian.limitValue', {
                count: filters.limit_per_endpoint,
            }),
        },
        {
            icon: 'sort',
            label: t('chat.activities.humanitarian.sort'),
            value: formatSort(filters.sort),
        },
        {
            icon: 'emergency',
            label: t('chat.activities.humanitarian.disasterStatus'),
            value: formatDisasterStatus(filters.disaster_status),
        },
    ];
});
const visualizationResultsSummary = computed(() =>
    result.value ? String(result.value.items.length) : undefined,
);
const visualizationEmptyState = computed(() =>
    result.value && !result.value.items.length
        ? {
              icon: 'article',
              message: t('chat.activities.humanitarian.noResults'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return country.value
            ? t('chat.activities.humanitarian.searchingCountry', { country: country.value })
            : t('chat.activities.humanitarian.searching');
    }

    if (result.value) {
        const count = result.value.items.length;
        return t(
            count === 1
                ? 'chat.activities.humanitarian.result'
                : 'chat.activities.humanitarian.results',
            { count },
        );
    }

    return t(`chat.activities.status.${props.payload.status}`);
});

function formatDate(value: string | null): string {
    if (!value) {
        return t('chat.activities.humanitarian.unknownDate');
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(date);
}

function formatSort(sort: string[]): string {
    return sort.length === 1 && sort[0] === 'date.created:desc'
        ? t('chat.activities.humanitarian.newestFirst')
        : sort.join(', ');
}

function formatDisasterStatus(status: string): string {
    return status === 'current' ? t('chat.activities.humanitarian.current') : status;
}

function formatItemType(type: HumanitarianContextItem['type']): string {
    return t(`chat.activities.humanitarian.types.${type}`);
}

function formatSources(sources: string[], provider: string): string {
    return sources.length ? sources.join(' · ') : provider;
}

function itemExtraInfo(item: HumanitarianContextItem) {
    return [
        { icon: 'calendar_today', value: formatDate(item.time) },
        { icon: 'source', value: formatSources(item.sources, item.provider) },
    ];
}
</script>

<style scoped lang="scss">
.item-category {
    color: #475467;
    font-size: 11px;
}
</style>
