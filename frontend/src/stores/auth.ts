import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import type { KeycloakProfile } from 'keycloak-js';
import { keycloak } from 'src/boot/api';

const ADMIN_ROLE = 'humconnect-admin';

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

        const authenticated = await keycloak.init({
            onLoad: 'check-sso',
        });
        initialized.value = true;

        if (authenticated) {
            realmRoles.value = keycloak.tokenParsed?.realm_access?.roles || [];
            profile.value = await keycloak.loadUserProfile();
        }

        return authenticated;
    }

    async function login() {
        if (!initialized.value) {
            await init();
        }
        if (isAuthenticated.value) {
            return;
        }
        await keycloak.login();
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

    async function updateToken() {
        if (!initialized.value) {
            await init();
        }
        if (!keycloak.authenticated) {
            throw new Error('Not authenticated');
        }
        try {
            await keycloak.updateToken(30);
            realmRoles.value = keycloak.tokenParsed?.realm_access?.roles || [];
            return true;
        } catch (err) {
            await logout();
            throw err;
        }
    }

    return {
        accessToken,
        initialized,
        isAdmin,
        isAuthenticated,
        keycloak,
        profile,
        realmRoles,
        init,
        login,
        logout,
        updateToken,
    };
});
