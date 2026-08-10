import { computed, proxyRefs, readonly, ref } from 'vue';
import { defineQuery, useQuery } from '@pinia/colada';
import {
    DEFAULT_RECORDED_EVENT_LIST_SORT,
    getRecordedEventCountsByCountry,
    listRecordedEvents,
    type RecordedEventListSort,
} from 'src/utils/recordedEventsApi';
import type {
    EventTag,
    ProfessionCategory,
    RecordedEvent,
    RecordedEventCountsByCountry,
} from 'src/utils/model';

const EVENT_LIST_PAGE_SIZE = 10;

export interface DashboardFilters {
    keyword: string | null;
    tags: EventTag[];
    affectedProfessionCategories: ProfessionCategory[];
    responseProfessionCategories: ProfessionCategory[];
}

function emptyFilters(): DashboardFilters {
    return {
        keyword: null,
        tags: [],
        affectedProfessionCategories: [],
        responseProfessionCategories: [],
    };
}

function normalizeFilters(filters: DashboardFilters): DashboardFilters {
    return {
        keyword: filters.keyword?.trim() || null,
        tags: [...filters.tags].sort(),
        affectedProfessionCategories: [...filters.affectedProfessionCategories].sort(),
        responseProfessionCategories: [...filters.responseProfessionCategories].sort(),
    };
}

export const useDashboardData = defineQuery(() => {
    const draftFilters = ref<DashboardFilters>(emptyFilters());
    const appliedFilters = ref<DashboardFilters>(emptyFilters());
    const currentPage = ref(1);
    const eventListSort = ref<RecordedEventListSort>(DEFAULT_RECORDED_EVENT_LIST_SORT);

    const mapQuery = useQuery({
        key: () => ['recorded-events', 'country-counts', { filters: appliedFilters.value }],
        query: () => getRecordedEventCountsByCountry(appliedFilters.value),
        placeholderData: (previousData) => previousData,
    });

    const eventListQuery = useQuery({
        key: () => [
            'recorded-events',
            'list',
            {
                filters: appliedFilters.value,
                page: currentPage.value,
                pageSize: EVENT_LIST_PAGE_SIZE,
                sort: eventListSort.value,
            },
        ],
        query: () =>
            listRecordedEvents(
                appliedFilters.value,
                {
                    page: currentPage.value,
                    pageSize: EVENT_LIST_PAGE_SIZE,
                },
                eventListSort.value,
            ),
        placeholderData: (previousData) => previousData,
    });

    const mapData = computed(
        (): Readonly<RecordedEventCountsByCountry> => mapQuery.data.value ?? {},
    );
    const mapLoading = computed(() => mapQuery.isLoading.value);
    const mapError = computed(() => mapQuery.error.value?.message);
    const eventListData = computed<readonly RecordedEvent[]>(
        () => eventListQuery.data.value?.events ?? [],
    );
    const eventListLoading = computed(() => eventListQuery.isLoading.value);
    const eventListError = computed(() => eventListQuery.error.value?.message);
    const eventListTotalCount = computed(() => eventListQuery.data.value?.total_count ?? 0);
    const eventListTotalPages = computed(() => eventListQuery.data.value?.total_pages ?? 0);
    const hasAppliedFilters = computed(
        () =>
            Boolean(appliedFilters.value.keyword) ||
            appliedFilters.value.tags.length > 0 ||
            appliedFilters.value.affectedProfessionCategories.length > 0 ||
            appliedFilters.value.responseProfessionCategories.length > 0,
    );
    const loading = computed(() => mapLoading.value || eventListLoading.value);

    function applyFilters() {
        currentPage.value = 1;
        appliedFilters.value = normalizeFilters(draftFilters.value);
    }

    function clearFilters() {
        draftFilters.value = emptyFilters();
        currentPage.value = 1;
        appliedFilters.value = emptyFilters();
    }

    function setCurrentPage(page: number) {
        const lastPage = Math.max(eventListTotalPages.value, 1);
        if (Number.isInteger(page) && page >= 1 && page <= lastPage) {
            currentPage.value = page;
        }
    }

    function setEventListSort(sort: RecordedEventListSort) {
        if (sort !== eventListSort.value) {
            currentPage.value = 1;
            eventListSort.value = sort;
        }
    }

    async function refresh() {
        await Promise.all([mapQuery.refetch(), eventListQuery.refetch()]);
    }

    return proxyRefs({
        draftFilters,
        appliedFilters: readonly(appliedFilters),
        currentPage: readonly(currentPage),
        eventListSort: readonly(eventListSort),
        hasAppliedFilters,
        loading,
        mapData,
        mapLoading,
        mapError,
        eventListData,
        eventListLoading,
        eventListError,
        eventListTotalCount,
        eventListTotalPages,
        applyFilters,
        clearFilters,
        setCurrentPage,
        setEventListSort,
        refresh,
    });
});
