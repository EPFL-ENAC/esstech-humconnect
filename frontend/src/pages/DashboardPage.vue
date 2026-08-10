<template>
    <q-page class="dashboard-page">
        <section class="dashboard-content">
            <div class="header-row">
                <div>
                    <h1>{{ t('dashboard.title') }}</h1>
                    <p>{{ t('dashboard.subtitle') }}</p>
                </div>

                <q-btn
                    outline
                    color="primary"
                    icon="refresh"
                    :label="t('dashboard.refresh')"
                    :loading="loading"
                    @click="loadEvents"
                />
            </div>

            <q-card flat bordered class="filters-card">
                <q-card-section>
                    <h2 class="filters-title">{{ t('dashboard.filters.title') }}</h2>
                    <q-form class="filters-form" @submit.prevent="applyFilters">
                        <div class="filters-grid">
                            <q-input
                                v-model="draftFilters.keyword"
                                outlined
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.keyword')"
                            />
                            <q-select
                                v-model="draftFilters.tags"
                                outlined
                                multiple
                                use-chips
                                emit-value
                                map-options
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.tags')"
                                :options="tagOptions"
                            />
                            <q-select
                                v-model="draftFilters.affectedProfessionCategories"
                                outlined
                                multiple
                                use-chips
                                emit-value
                                map-options
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.affectedProfessions')"
                                :options="professionOptions"
                            />
                            <q-select
                                v-model="draftFilters.responseProfessionCategories"
                                outlined
                                multiple
                                use-chips
                                emit-value
                                map-options
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.responseProfessions')"
                                :options="professionOptions"
                            />
                        </div>
                        <div class="filter-actions">
                            <q-btn
                                flat
                                color="primary"
                                :disable="loading"
                                :label="t('dashboard.filters.clear')"
                                @click="clearFilters"
                            />
                            <q-btn
                                color="primary"
                                icon="filter_alt"
                                type="submit"
                                :disable="loading"
                                :loading="loading"
                                :label="t('dashboard.filters.apply')"
                            />
                        </div>
                    </q-form>
                </q-card-section>
            </q-card>

            <EventCountryMap
                :data="dashboardStore.mapData"
                :loading="dashboardStore.mapLoading"
                :error="dashboardStore.mapError"
            />

            <RecordedEventList
                v-model:page="listPage"
                v-model:sort="listSort"
                :data="dashboardStore.currentPageData"
                :loading="dashboardStore.eventListLoading"
                :error="dashboardStore.eventListError"
                :filtered="hasAppliedFilters"
                :page-count="dashboardStore.eventListTotalPages"
            />
        </section>
    </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import EventCountryMap from 'src/components/dashboard/EventCountryMap.vue';
import RecordedEventList from 'src/components/dashboard/RecordedEventList.vue';
import { useDashboardStore } from 'src/stores/dashboard';
import { eventTags, professionCategories } from 'src/utils/model';
import type { EventTag, ProfessionCategory } from 'src/utils/model';

interface DashboardFilters {
    keyword: string | null;
    tags: EventTag[];
    affectedProfessionCategories: ProfessionCategory[];
    responseProfessionCategories: ProfessionCategory[];
}

function emptyFilters(): DashboardFilters {
    return {
        keyword: '',
        tags: [],
        affectedProfessionCategories: [],
        responseProfessionCategories: [],
    };
}

const { t } = useI18n();
const dashboardStore = useDashboardStore();
const appliedFilters = ref<DashboardFilters>(emptyFilters());
const draftFilters = ref<DashboardFilters>(emptyFilters());
const loading = computed(() => dashboardStore.mapLoading || dashboardStore.eventListLoading);
const listPage = computed({
    get: () => dashboardStore.currentPage,
    set: (page: number) => {
        void dashboardStore.setCurrentListPage(page);
    },
});
const listSort = computed({
    get: () => dashboardStore.eventListSort,
    set: (sort) => {
        void dashboardStore.setEventListSort(sort);
    },
});

const tagOptions = computed(() =>
    eventTags.map((tag) => ({
        label: t(`dashboard.tags.${tag}`),
        value: tag,
    })),
);

const professionOptions = computed(() =>
    professionCategories.map((category) => ({
        label: t(`profile.categories.${category}`),
        value: category,
    })),
);

const hasAppliedFilters = computed(
    () =>
        Boolean(appliedFilters.value.keyword?.trim()) ||
        appliedFilters.value.tags.length > 0 ||
        appliedFilters.value.affectedProfessionCategories.length > 0 ||
        appliedFilters.value.responseProfessionCategories.length > 0,
);

async function loadEvents() {
    await dashboardStore.updateFilters(appliedFilters.value);
}

async function applyFilters() {
    appliedFilters.value = {
        keyword: draftFilters.value.keyword?.trim() || '',
        tags: [...draftFilters.value.tags],
        affectedProfessionCategories: [...draftFilters.value.affectedProfessionCategories],
        responseProfessionCategories: [...draftFilters.value.responseProfessionCategories],
    };
    await loadEvents();
}

async function clearFilters() {
    draftFilters.value = emptyFilters();
    appliedFilters.value = emptyFilters();
    await loadEvents();
}

onMounted(() => {
    void loadEvents();
});
</script>

<style scoped lang="scss">
.dashboard-page {
    padding: 32px;
}

.dashboard-content {
    max-width: 1080px;
}

.header-row {
    align-items: center;
    display: flex;
    gap: 24px;
    justify-content: space-between;
    margin-bottom: 24px;
}

h1 {
    font-size: 32px;
    line-height: 1.2;
    margin: 0 0 6px;
}

p {
    color: #667085;
    margin: 0;
}

.filters-card {
    margin-bottom: 20px;
}

.filters-title {
    font-size: 18px;
    margin: 0 0 16px;
}

.filters-form {
    display: grid;
    gap: 16px;
}

.filters-grid {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

.filter-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
}

@media (max-width: 760px) {
    .dashboard-page {
        padding: 20px;
    }

    .header-row {
        align-items: stretch;
        flex-direction: column;
    }

    .filters-grid {
        grid-template-columns: 1fr;
    }

    .filter-actions {
        justify-content: stretch;
    }

    .filter-actions :deep(.q-btn) {
        flex: 1;
    }
}
</style>
