import { baseUrl } from 'src/boot/api';
import { authenticatedFetch } from 'src/utils/apiFetch';
import { getI18nT } from 'src/utils/i18n';
import type { UserProfile, UserProfileEditableFields } from 'src/utils/model';

export async function getProfile(): Promise<UserProfile> {
    const t = getI18nT();
    const response = await authenticatedFetch(`${baseUrl}/profile`);

    if (!response.ok) {
        throw new Error(t('errors.loadProfile'));
    }

    return (await response.json()) as UserProfile;
}

export async function updateProfile(payload: UserProfileEditableFields): Promise<UserProfile> {
    const t = getI18nT();
    const response = await authenticatedFetch(`${baseUrl}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(t('errors.saveProfile'));
    }

    return (await response.json()) as UserProfile;
}
