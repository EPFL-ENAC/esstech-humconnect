<template>
    <div class="event-list-toolbar">
        <q-select
            :model-value="dashboardData.eventListSort"
            class="event-list-sort"
            outlined
            dense
            emit-value
            map-options
            :disable="dashboardData.eventListLoading"
            :label="t('dashboard.sort.label')"
            :options="sortOptions"
            @update:model-value="dashboardData.setEventListSort"
        />
    </div>

    <q-banner v-if="dashboardData.eventListError" class="bg-red-1 text-red-9 q-mb-md" rounded>
        {{ dashboardData.eventListError }}
    </q-banner>

    <q-list bordered separator class="event-list">
        <q-item v-if="dashboardData.eventListLoading">
            <q-item-section>{{ t('dashboard.loading') }}</q-item-section>
        </q-item>

        <q-item v-else-if="dashboardData.eventListData.length === 0">
            <q-item-section>
                {{
                    dashboardData.hasAppliedFilters
                        ? t('dashboard.filteredEmpty')
                        : t('dashboard.empty')
                }}
            </q-item-section>
        </q-item>

        <template v-else>
            <RecordedEventListItem
                v-for="event in dashboardData.eventListData"
                :key="event.id"
                :event="event"
            />
        </template>
    </q-list>

    <div v-if="dashboardData.eventListTotalPages > 1" class="event-list-pagination">
        <q-pagination
            :model-value="dashboardData.currentPage"
            :max="dashboardData.eventListTotalPages"
            :disable="dashboardData.eventListLoading"
            boundary-numbers
            direction-links
            @update:model-value="dashboardData.setCurrentPage"
        />
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import RecordedEventListItem from 'src/components/dashboard/RecordedEventListItem.vue';
import { useDashboardData } from 'src/queries/dashboard';
import { recordedEventListSorts } from 'src/utils/recordedEventsApi';

const { t } = useI18n();
const dashboardData = useDashboardData();
const sortOptions = computed(() =>
    recordedEventListSorts.map((value) => ({
        label: t(`dashboard.sort.options.${value}`),
        value,
    })),
);
</script>

<style scoped lang="scss">
.event-list {
    background: white;
}

.event-list-toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 12px;
}

.event-list-sort {
    width: 260px;
}

.event-list-pagination {
    display: flex;
    justify-content: center;
    padding-top: 20px;
}
</style>
