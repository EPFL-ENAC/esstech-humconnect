import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import { useAuthStore } from 'src/stores/auth';
import type {
    EventTag,
    ListRecordedEventsResponse,
    ProfessionCategory,
    RecordedEvent,
} from 'src/utils/model';

export interface RecordedEventFilters {
    keyword?: string | null;
    tags?: readonly EventTag[];
    affectedProfessionCategories?: readonly ProfessionCategory[];
    responseProfessionCategories?: readonly ProfessionCategory[];
}

export async function listRecordedEvents(
    filters: RecordedEventFilters = {},
): Promise<RecordedEvent[]> {
    const t = getI18nT();
    const authStore = useAuthStore();
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

    const query = params.toString();
    const url = `${baseUrl}/recorded-events${query ? `?${query}` : ''}`;
    const response = await authStore.fetchApi(url);

    if (!response.ok) {
        throw new Error(t('errors.loadRecordedEvents'));
    }

    const payload = (await response.json()) as ListRecordedEventsResponse;
    return payload.events;
}
