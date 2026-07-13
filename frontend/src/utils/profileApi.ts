import { baseUrl } from 'src/boot/api';
import { useAuthStore } from 'src/stores/auth';
import { getI18nT } from 'src/utils/i18n';
import type {
    ListAddressSuggestionsResponse,
    UserProfile,
    UserProfileEditableFields,
} from 'src/utils/model';

export async function getProfile(): Promise<UserProfile> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(`${baseUrl}/profile`);

    if (!response.ok) {
        throw new Error(t('errors.loadProfile'));
    }

    return (await response.json()) as UserProfile;
}

export async function updateProfile(payload: UserProfileEditableFields): Promise<UserProfile> {
    const t = getI18nT();
    const authStore = useAuthStore();
    const response = await authStore.fetchApi(`${baseUrl}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(t('errors.saveProfile'));
    }

    return (await response.json()) as UserProfile;
}

export async function searchAddressSuggestions(
    query: string,
): Promise<ListAddressSuggestionsResponse> {
    const authStore = useAuthStore();
    const params = new URLSearchParams({ q: query });
    const response = await authStore.fetchApi(
        `${baseUrl}/profile/center-address/search?${params.toString()}`,
    );

    if (!response.ok) {
        return { suggestions: [] };
    }

    return (await response.json()) as ListAddressSuggestionsResponse;
}
