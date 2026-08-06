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
            <div v-if="payload.status === 'running'" class="visualization-loading">
                <q-spinner-dots size="22px" color="primary" />
            </div>
            <div v-else-if="result" class="humanitarian-context">
                <section>
                    <h4 class="section-title">
                        {{ t('chat.activities.humanitarian.filters') }}
                    </h4>
                    <div class="filter-pills">
                        <q-chip dense outline>
                            <span class="filter-label">
                                {{ t('chat.activities.humanitarian.provider') }}:
                            </span>
                            {{ result.filters.provider }}
                        </q-chip>
                        <q-chip dense outline>
                            <span class="filter-label">
                                {{ t('chat.activities.humanitarian.country') }}:
                            </span>
                            {{ result.filters.country }}
                        </q-chip>
                        <q-chip dense outline>
                            <span class="filter-label">
                                {{ t('chat.activities.humanitarian.createdFrom') }}:
                            </span>
                            {{ formatDate(result.filters.created_from) }}
                        </q-chip>
                        <q-chip dense outline>
                            <span class="filter-label">
                                {{ t('chat.activities.humanitarian.limit') }}:
                            </span>
                            {{
                                t('chat.activities.humanitarian.limitValue', {
                                    count: result.filters.limit_per_endpoint,
                                })
                            }}
                        </q-chip>
                        <q-chip dense outline>
                            <span class="filter-label">
                                {{ t('chat.activities.humanitarian.sort') }}:
                            </span>
                            {{ formatSort(result.filters.sort) }}
                        </q-chip>
                        <q-chip dense outline>
                            <span class="filter-label">
                                {{ t('chat.activities.humanitarian.disasterStatus') }}:
                            </span>
                            {{ formatDisasterStatus(result.filters.disaster_status) }}
                        </q-chip>
                    </div>
                    <div class="report-query">
                        <div>{{ t('chat.activities.humanitarian.reportQuery') }}</div>
                        <p>{{ result.filters.report_query }}</p>
                    </div>
                </section>

                <q-banner v-if="result.warnings?.length" dense rounded class="warning-banner">
                    <template #avatar><q-icon name="warning_amber" /></template>
                    <ul>
                        <li v-for="warning in result.warnings" :key="warning">{{ warning }}</li>
                    </ul>
                </q-banner>

                <section class="results-section">
                    <ChatCardGallery v-if="result.items.length">
                        <component
                            :is="item.source_url ? 'a' : 'article'"
                            v-for="item in result.items"
                            :key="`${item.type}-${item.id}`"
                            class="context-card"
                            :class="{ 'context-card-link': item.source_url }"
                            :href="item.source_url ?? undefined"
                            :target="item.source_url ? '_blank' : undefined"
                            :rel="item.source_url ? 'noopener noreferrer' : undefined"
                        >
                            <div class="card-heading">
                                <span class="item-type">{{ formatItemType(item.type) }}</span>
                                <q-icon v-if="item.source_url" name="open_in_new" size="15px" />
                            </div>
                            <h5>{{ item.title }}</h5>
                            <div class="item-category">{{ item.category }}</div>
                            <dl class="card-meta">
                                <div>
                                    <dt><q-icon name="calendar_today" /></dt>
                                    <dd>{{ formatDate(item.time) }}</dd>
                                </div>
                                <div>
                                    <dt><q-icon name="source" /></dt>
                                    <dd>{{ formatSources(item.sources, item.provider) }}</dd>
                                </div>
                            </dl>
                        </component>
                    </ChatCardGallery>
                    <div v-else class="empty-results">
                        <q-icon name="article" size="22px" />
                        <span>{{ t('chat.activities.humanitarian.noResults') }}</span>
                    </div>
                </section>
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
import type { ToolCallPayload } from 'src/utils/model';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';

interface HumanitarianContextFilters {
    provider: string;
    country: string;
    created_from: string;
    limit_per_endpoint: number;
    sort: string[];
    report_query: string;
    disaster_status: string;
}

interface HumanitarianContextItem {
    provider: string;
    type: 'report' | 'disaster';
    id: string;
    title: string;
    category: string;
    time: string | null;
    source_url: string | null;
    sources: string[];
}

interface HumanitarianContextResult {
    country: string;
    filters: HumanitarianContextFilters;
    items: HumanitarianContextItem[];
    warnings?: string[];
}

const props = defineProps<{
    payload: ToolCallPayload;
}>();

const { locale, t } = useI18n();

function parseResult(answer: string | null): HumanitarianContextResult | null {
    if (!answer) {
        return null;
    }

    try {
        const value = JSON.parse(answer) as HumanitarianContextResult;
        if (
            !value?.filters ||
            !Array.isArray(value.filters.sort) ||
            !Array.isArray(value.items) ||
            (value.warnings !== undefined && !Array.isArray(value.warnings))
        ) {
            return null;
        }
        return value;
    } catch {
        return null;
    }
}

const result = computed(() =>
    props.payload.status === 'finished' ? parseResult(props.payload.answer) : null,
);
const country = computed(() => {
    const value = props.payload.arguments?.country_name;
    return typeof value === 'string' ? value : '';
});
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
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
</script>

<style scoped lang="scss">
.visualization-loading {
    align-items: center;
    color: #667085;
    display: flex;
    min-height: 48px;
}

.section-title {
    color: #344054;
    font-size: 12px;
    font-weight: 650;
    margin: 0 0 6px;
}

.filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.filter-pills :deep(.q-chip) {
    color: #475467;
    font-size: 10px;
    margin: 0;
    max-width: 100%;
}

.filter-pills :deep(.q-chip__content) {
    overflow-wrap: anywhere;
    white-space: normal;
}

.filter-label {
    color: #667085;
    font-weight: 650;
    margin-right: 3px;
}

.report-query {
    background: #f8fafc;
    border: 1px solid #eaecf0;
    border-radius: 7px;
    margin-top: 8px;
    padding: 7px 8px;
}

.report-query > div {
    color: #667085;
    font-size: 10px;
    font-weight: 650;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}

.report-query p {
    color: #344054;
    font-size: 12px;
    margin: 2px 0 0;
    overflow-wrap: anywhere;
}

.warning-banner {
    background: #fffaeb;
    color: #7a2e0e;
    font-size: 12px;
    margin-top: 10px;
}

.warning-banner ul {
    margin: 0;
    padding-left: 18px;
}

.results-section {
    margin-top: 14px;
}

.context-card {
    background: white;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    color: #344054;
    display: flex;
    flex-direction: column;
    min-height: 178px;
    padding: 11px;
    text-decoration: none;
}

.context-card-link {
    cursor: pointer;
    transition:
        border-color 140ms ease,
        box-shadow 140ms ease,
        transform 140ms ease;
}

.context-card-link:hover,
.context-card-link:focus-visible {
    border-color: #84adff;
    box-shadow: 0 4px 12px rgba(21, 112, 239, 0.12);
    outline: none;
    transform: translateY(-1px);
}

.card-heading {
    align-items: center;
    color: #1570ef;
    display: flex;
    justify-content: space-between;
}

.item-type {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.context-card h5 {
    color: #101828;
    display: -webkit-box;
    font-size: 13px;
    font-weight: 650;
    line-height: 1.35;
    margin: 8px 0 6px;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.item-category {
    color: #475467;
    font-size: 11px;
    margin-bottom: 10px;
}

.card-meta {
    color: #667085;
    font-size: 11px;
    margin: auto 0 0;
}

.card-meta > div {
    align-items: flex-start;
    display: flex;
    gap: 5px;
    margin-top: 5px;
}

.card-meta dt,
.card-meta dd {
    margin: 0;
}

.empty-results {
    align-items: center;
    background: #f8fafc;
    border: 1px dashed #d0d5dd;
    border-radius: 8px;
    color: #667085;
    display: flex;
    gap: 8px;
    justify-content: center;
    min-height: 72px;
    padding: 12px;
}
</style>
