import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import { authenticatedFetch } from 'src/utils/apiFetch';
import type { ListRecordedEventsResponse, RecordedEvent } from 'src/utils/model';

export async function listRecordedEvents(): Promise<RecordedEvent[]> {
    const t = getI18nT();
    const response = await authenticatedFetch(`${baseUrl}/recorded-events`);

    if (!response.ok) {
        throw new Error(t('errors.loadRecordedEvents'));
    }

    const payload = (await response.json()) as ListRecordedEventsResponse;
    return payload.events;
}
