import { baseUrl } from 'src/boot/api';
import { getI18nT } from 'src/utils/i18n';
import { useAuthStore } from 'src/stores/auth';
import type {
    EventTag,
    ListRecordedEventsResponse,
    ProfessionCategory,
    RecordedEventCountsByCountry,
} from 'src/utils/model';

export interface RecordedEventFilters {
    keyword?: string | null;
    tags?: readonly EventTag[];
    affectedProfessionCategories?: readonly ProfessionCategory[];
    responseProfessionCategories?: readonly ProfessionCategory[];
}

export interface RecordedEventPagination {
    page: number;
    pageSize: number;
}

export const recordedEventListSorts = [
    'event_date_asc',
    'event_date_desc',
    'added_date_asc',
    'added_date_desc',
] as const;

export type RecordedEventListSort = (typeof recordedEventListSorts)[number];

export const DEFAULT_RECORDED_EVENT_LIST_SORT: RecordedEventListSort = 'event_date_desc';

function queryRecordedEvents(
    filters: RecordedEventFilters,
    pagination?: RecordedEventPagination,
    sort?: RecordedEventListSort,
): string {
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
    if (pagination) {
        params.set('page', String(pagination.page));
        params.set('page_size', String(pagination.pageSize));
    }
    if (sort) {
        params.set('sort', sort);
    }
    return params.toString();
}

function recordedEventsUrl(
    path: string,
    filters: RecordedEventFilters,
    pagination?: RecordedEventPagination,
    sort?: RecordedEventListSort,
): string {
    const query = queryRecordedEvents(filters, pagination, sort);
    return `${baseUrl}/recorded-events${path}${query ? `?${query}` : ''}`;
}

export async function listRecordedEvents(
    filters: RecordedEventFilters = {},
    pagination: RecordedEventPagination,
    sort: RecordedEventListSort,
): Promise<ListRecordedEventsResponse> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(recordedEventsUrl('', filters, pagination, sort));

    if (!response.ok) {
        throw new Error(t('errors.loadRecordedEvents'));
    }

    return (await response.json()) as ListRecordedEventsResponse;
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
