import { ref } from 'vue';
import { defineStore } from 'pinia';
import { getI18nT } from 'src/utils/i18n';
import {
    getRecordedEventCountsByCountry,
    listRecordedEvents,
    type RecordedEventFilters,
} from 'src/utils/recordedEventsApi';
import type { RecordedEvent, RecordedEventCountsByCountry } from 'src/utils/model';

export const useDashboardStore = defineStore('dashboard', () => {
    const t = getI18nT();
    const mapLoading = ref(true);
    const mapError = ref('');
    const mapData = ref<RecordedEventCountsByCountry>({});
    const eventListLoading = ref(true);
    const eventListError = ref('');
    const eventListData = ref<RecordedEvent[]>([]);

    async function loadMap(filters: RecordedEventFilters) {
        mapLoading.value = true;
        mapError.value = '';

        try {
            mapData.value = await getRecordedEventCountsByCountry(filters);
        } catch (err) {
            mapError.value = err instanceof Error ? err.message : t('errors.loadRecordedEventMap');
        } finally {
            mapLoading.value = false;
        }
    }

    async function loadEventList(filters: RecordedEventFilters) {
        eventListLoading.value = true;
        eventListError.value = '';

        try {
            eventListData.value = await listRecordedEvents(filters);
        } catch (err) {
            eventListError.value =
                err instanceof Error ? err.message : t('errors.loadRecordedEvents');
        } finally {
            eventListLoading.value = false;
        }
    }

    async function load(filters: RecordedEventFilters = {}) {
        await Promise.all([loadMap(filters), loadEventList(filters)]);
    }

    return {
        mapLoading,
        mapError,
        mapData,
        eventListLoading,
        eventListError,
        eventListData,
        load,
    };
});
