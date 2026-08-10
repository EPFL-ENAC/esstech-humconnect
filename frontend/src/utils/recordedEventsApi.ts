import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import { useAuthStore } from 'src/stores/auth';
import type {
    EventTag,
    ListRecordedEventsResponse,
    ProfessionCategory,
    RecordedEvent,
    RecordedEventCountsByCountry,
} from 'src/utils/model';

export interface RecordedEventFilters {
    keyword?: string | null;
    tags?: readonly EventTag[];
    affectedProfessionCategories?: readonly ProfessionCategory[];
    responseProfessionCategories?: readonly ProfessionCategory[];
}

function queryRecordedEvents(filters: RecordedEventFilters): string {
    const params = new URLSearchParams();
    const keyword = filters.keyword?.trim();
    if (keyword) {
        params.set('keyword', keyword);
    }
    filters.tags?.forEach((tag) => params.append('tags', tag));
    filters.affectedProfessionCategories?.forEach((category) =>
        params.append('affected_profession_categories', category),
    );
    filters.responseProfessionCategories?.forEach((category) =>
        params.append('response_profession_categories', category),
    );
    return params.toString();
}

function recordedEventsUrl(path: string, filters: RecordedEventFilters): string {
    const query = queryRecordedEvents(filters);
    return `${baseUrl}/recorded-events${path}${query ? `?${query}` : ''}`;
}

export async function listRecordedEvents(
    filters: RecordedEventFilters = {},
): Promise<RecordedEvent[]> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(recordedEventsUrl('', filters));

    if (!response.ok) {
        throw new Error(t('errors.loadRecordedEvents'));
    }

    const payload = (await response.json()) as ListRecordedEventsResponse;
    return payload.events;
}

export async function getRecordedEventCountsByCountry(
    filters: RecordedEventFilters = {},
): Promise<RecordedEventCountsByCountry> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(recordedEventsUrl('/count-by-country', filters));

    if (!response.ok) {
        throw new Error(t('errors.loadRecordedEventMap'));
    }

    return (await response.json()) as RecordedEventCountsByCountry;
}
