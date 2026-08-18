import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import type { KeycloakProfile } from 'keycloak-js';
import { keycloak } from 'src/boot/api';

const ADMIN_ROLE = 'humconnect-admin';

interface FetchApiOptions {
    retries?: number;
}

export const useAuthStore = defineStore('auth', () => {
    const profile = ref<KeycloakProfile>();
    const realmRoles = ref<string[]>([]);
    const initialized = ref(false);

    const isAuthenticated = computed(() => profile.value !== undefined);
    const isAdmin = computed(() => realmRoles.value.includes(ADMIN_ROLE));
    const accessToken = computed(() => keycloak.token);

    async function init() {
        if (initialized.value) {
            return keycloak.authenticated === true;
        }

        profile.value = undefined;
        realmRoles.value = [];

        try {
            const authenticated = await keycloak.init({
                checkLoginIframe: false,
            });
            initialized.value = true;

            if (authenticated) {
                realmRoles.value = keycloak.tokenParsed?.realm_access?.roles || [];
                profile.value = await keycloak.loadUserProfile();
            }

            return authenticated;
        } catch (error) {
            console.error('Failed to initialize Keycloak:', error);
            initialized.value = true;
            return false;
        }
    }

    async function login(redirectUri?: string) {
        if (!initialized.value) {
            await init();
        }
        if (isAuthenticated.value) {
            return;
        }
        await keycloak.login(redirectUri ? { redirectUri } : undefined);
    }

    async function logout() {
        if (!initialized.value) {
            profile.value = undefined;
            realmRoles.value = [];
            return;
        }
        await keycloak.logout({
            redirectUri: window.location.origin,
        });
        profile.value = undefined;
        realmRoles.value = [];
    }

    async function updateToken(minValidity = 30) {
        if (!initialized.value) {
            await init();
        }
        if (!keycloak.authenticated) {
            throw new Error('Not authenticated');
        }
        try {
            await keycloak.updateToken(minValidity);
            realmRoles.value = keycloak.tokenParsed?.realm_access?.roles || [];
            return true;
        } catch (err) {
            await logout();
            throw err;
        }
    }

    async function fetchApi(
        input: RequestInfo | URL,
        init: RequestInit = {},
        options: FetchApiOptions = {},
    ): Promise<Response> {
        const retries = options.retries ?? 1;
        if (!Number.isInteger(retries) || retries < 0) {
            throw new RangeError('retries must be a non-negative integer');
        }

        const request = new Request(input, init);
        await updateToken();

        for (let attempt = 0; ; attempt += 1) {
            const headers = new Headers(request.headers);
            headers.set('Authorization', `Bearer ${keycloak.token}`);

            const response = await fetch(new Request(request.clone(), { headers }));
            if (response.status !== 401 || attempt >= retries) {
                return response;
            }

            await updateToken(-1);
        }
    }

    return {
        accessToken,
        initialized,
        isAdmin,
        isAuthenticated,
        profile,
        realmRoles,
        fetchApi,
        init,
        login,
        logout,
        updateToken,
    };
});
