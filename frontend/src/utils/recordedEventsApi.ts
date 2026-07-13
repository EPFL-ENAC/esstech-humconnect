import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import { useAuthStore } from 'src/stores/auth';
import type { ListRecordedEventsResponse, RecordedEvent } from 'src/utils/model';

export async function listRecordedEvents(): Promise<RecordedEvent[]> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(`${baseUrl}/recorded-events`);

    if (!response.ok) {
        throw new Error(t('errors.loadRecordedEvents'));
    }

    const payload = (await response.json()) as ListRecordedEventsResponse;
    return payload.events;
}
