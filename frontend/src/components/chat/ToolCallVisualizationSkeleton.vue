<template>
    <div class="visualization-skeleton q-pt-sm" :style="{ '--visualization-accent': accentColor }">
        <div v-if="loading" class="visualization-loading">
            <q-spinner-dots size="22px" />
        </div>
        <template v-else>
            <section v-if="query" class="query-section">
                <h4 class="section-title">
                    <q-icon v-if="query.icon" :name="query.icon" size="1.5rem" />
                    {{ query.label ?? t('chat.activities.visualization.query') }}
                </h4>
                <slot name="query-value">
                    <span class="query-value">{{ query.value }}</span>
                </slot>
            </section>

            <div v-if="filters?.length" class="filter-list">
                <q-chip
                    v-for="(filter, index) in filters"
                    :key="index"
                    square
                    size="sm"
                    outline
                    :color="accentColor"
                    class="filter-chip"
                >
                    <q-icon
                        v-if="filter.icon"
                        :name="filter.icon"
                        size="1rem"
                        class="filter-icon"
                    />
                    <span v-if="filter.label" class="filter-label">{{ filter.label }}:</span>
                    <span class="filter-value">{{ filter.value }}</span>
                </q-chip>
            </div>

            <q-banner v-if="warnings?.length" dense rounded class="warning-banner">
                <template #avatar><q-icon name="warning_amber" /></template>
                <ul>
                    <li v-for="(warning, index) in warnings" :key="index">{{ warning }}</li>
                </ul>
            </q-banner>

            <section class="results-section q-mt-lg">
                <h4 class="section-title">
                    {{ resultsLabel ?? t('chat.activities.visualization.results') }}
                    <span v-if="resultsSummary">({{ resultsSummary }})</span>
                </h4>
                <div v-if="emptyState" class="empty-results">
                    <q-icon :name="emptyState.icon ?? 'inbox'" size="22px" />
                    <span>{{ emptyState.message }}</span>
                </div>
                <slot v-else name="results" />
            </section>
        </template>
    </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

interface VisualizationDetail {
    value: string;
    label?: string | undefined;
    icon?: string | undefined;
}

interface VisualizationEmptyState {
    message: string;
    icon?: string | undefined;
}

defineProps<{
    loading: boolean;
    accentColor?: string | undefined;
    query?: VisualizationDetail | null | undefined;
    filters?: VisualizationDetail[] | undefined;
    warnings?: string[] | null | undefined;
    resultsLabel?: string | undefined;
    resultsSummary?: string | undefined;
    emptyState?: VisualizationEmptyState | null | undefined;
}>();

const { t } = useI18n();
</script>

<style scoped lang="scss">
.visualization-skeleton {
    --visualization-accent: #667085;
}

.visualization-loading {
    align-items: center;
    color: var(--visualization-accent);
    display: flex;
    min-height: 48px;
}

.query-section,
.results-section {
    min-width: 0;
}

.section-title {
    align-items: center;
    color: #667085;
    display: flex;
    font-size: 1rem;
    font-weight: 650;
    gap: 0.5rem;
    line-height: 1;
    margin: 0 0 0.25rem;
}

.section-title span {
    font-weight: 500;
}

.query-value {
    color: #344054;
    font-size: 12px;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}

.filter-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
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

.empty-results {
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

.filter-chip {
    color: var(--visualization-accent);
    border-color: var(--visualization-accent);
}

.filter-icon {
    grid-area: filter-icon;
}

.filter-label {
    grid-area: filter-label;
    font-weight: 600;
    margin-left: 0.125rem;
}

.filter-value {
    grid-area: filter-value;
    margin-left: 0.25rem;
}
</style>
