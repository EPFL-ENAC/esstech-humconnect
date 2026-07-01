import { useAuthStore } from 'src/stores/auth';

export async function authHeaders(): Promise<HeadersInit> {
    const authStore = useAuthStore();
    await authStore.updateToken();
    return {
        Authorization: `Bearer ${authStore.accessToken}`,
    };
}

export async function authenticatedFetch(
    input: RequestInfo | URL,
    init: RequestInit = {},
): Promise<Response> {
    const headers = new Headers(init.headers);
    const authStore = useAuthStore();
    await authStore.updateToken();
    headers.set('Authorization', `Bearer ${authStore.accessToken}`);

    return fetch(input, {
        ...init,
        headers,
    });
}
