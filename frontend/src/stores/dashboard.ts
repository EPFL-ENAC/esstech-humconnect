import { computed, reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { getI18nT } from 'src/utils/i18n';
import {
    DEFAULT_RECORDED_EVENT_LIST_SORT,
    getRecordedEventCountsByCountry,
    listRecordedEvents,
    type RecordedEventFilters,
    type RecordedEventListSort,
} from 'src/utils/recordedEventsApi';
import type { RecordedEvent, RecordedEventCountsByCountry } from 'src/utils/model';

const EVENT_LIST_PAGE_SIZE = 5;

function copyFilters(filters: RecordedEventFilters): RecordedEventFilters {
    return {
        keyword: filters.keyword?.trim() || null,
        tags: [...(filters.tags ?? [])],
        affectedProfessionCategories: [...(filters.affectedProfessionCategories ?? [])],
        responseProfessionCategories: [...(filters.responseProfessionCategories ?? [])],
    };
}

export const useDashboardStore = defineStore('dashboard', () => {
    const t = getI18nT();
    const mapLoading = ref(true);
    const mapError = ref('');
    const mapData = ref<RecordedEventCountsByCountry>({});
    const eventListLoading = ref(true);
    const eventListError = ref('');
    const eventListData = reactive(new Map<number, readonly RecordedEvent[]>());
    const currentPage = ref(1);
    const currentPageData = computed<readonly RecordedEvent[]>(
        () => eventListData.get(currentPage.value) ?? [],
    );
    const eventListTotalPages = ref(0);
    const eventListTotalCount = ref(0);
    const eventListSort = ref<RecordedEventListSort>(DEFAULT_RECORDED_EVENT_LIST_SORT);

    let currentFilters: RecordedEventFilters = {};
    let filtersVersion = 0;
    let eventListVersion = 0;
    let eventListRequestId = 0;

    async function loadMap(filters: RecordedEventFilters, version: number) {
        mapLoading.value = true;
        mapError.value = '';

        try {
            const data = await getRecordedEventCountsByCountry(filters);
            if (version === filtersVersion) {
                mapData.value = data;
            }
        } catch (err) {
            if (version === filtersVersion) {
                mapError.value =
                    err instanceof Error ? err.message : t('errors.loadRecordedEventMap');
            }
        } finally {
            if (version === filtersVersion) {
                mapLoading.value = false;
            }
        }
    }

    async function loadEventListPage(
        filters: RecordedEventFilters,
        sort: RecordedEventListSort,
        page: number,
        version: number,
    ) {
        const requestId = ++eventListRequestId;
        eventListLoading.value = true;
        eventListError.value = '';

        try {
            const response = await listRecordedEvents(
                filters,
                {
                    page,
                    pageSize: EVENT_LIST_PAGE_SIZE,
                },
                sort,
            );
            if (version !== eventListVersion) {
                return;
            }

            eventListData.set(page, Object.freeze([...response.events]));
            if (requestId === eventListRequestId) {
                eventListTotalPages.value = response.total_pages;
                eventListTotalCount.value = response.total_count;
                currentPage.value = page;
            }
        } catch (err) {
            if (version === eventListVersion && requestId === eventListRequestId) {
                eventListError.value =
                    err instanceof Error ? err.message : t('errors.loadRecordedEvents');
            }
        } finally {
            if (version === eventListVersion && requestId === eventListRequestId) {
                eventListLoading.value = false;
            }
        }
    }

    function invalidateEventList() {
        const version = ++eventListVersion;
        eventListRequestId += 1;
        eventListData.clear();
        currentPage.value = 1;
        eventListTotalPages.value = 0;
        eventListTotalCount.value = 0;
        return version;
    }

    async function updateFilters(filters: RecordedEventFilters = {}) {
        const mapVersion = ++filtersVersion;
        currentFilters = copyFilters(filters);
        const listVersion = invalidateEventList();

        await Promise.all([
            loadMap(currentFilters, mapVersion),
            loadEventListPage(currentFilters, eventListSort.value, 1, listVersion),
        ]);
    }

    async function setCurrentListPage(page: number) {
        const lastPage = Math.max(eventListTotalPages.value, 1);
        if (!Number.isInteger(page) || page < 1 || page > lastPage) {
            return;
        }

        if (eventListData.has(page)) {
            eventListRequestId += 1;
            eventListLoading.value = false;
            eventListError.value = '';
            currentPage.value = page;
            return;
        }

        await loadEventListPage(currentFilters, eventListSort.value, page, eventListVersion);
    }

    async function setEventListSort(sort: RecordedEventListSort) {
        if (sort === eventListSort.value) {
            return;
        }

        eventListSort.value = sort;
        const version = invalidateEventList();
        await loadEventListPage(currentFilters, sort, 1, version);
    }

    return {
        mapLoading,
        mapError,
        mapData,
        eventListLoading,
        eventListError,
        currentPage,
        currentPageData,
        eventListTotalPages,
        eventListTotalCount,
        eventListSort,
        updateFilters,
        setCurrentListPage,
        setEventListSort,
    };
});
