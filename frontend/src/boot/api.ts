import Keycloak from 'keycloak-js';

interface CustomWindow extends Window {
    env: {
        API_URL: string;
        API_PATH: string;
        KEYCLOAK_URL?: string;
        KEYCLOAK_REALM?: string;
        AUTH_CLIENT_ID: string;
    };
}

const appEnv = (window as unknown as CustomWindow).env;
export const baseUrl = `${appEnv.API_URL}${appEnv.API_PATH}`;
export const keycloak = new Keycloak({
    url: appEnv.KEYCLOAK_URL || 'https://enac-it-sso.epfl.ch',
    realm: appEnv.KEYCLOAK_REALM || 'ENAC',
    clientId: appEnv.AUTH_CLIENT_ID,
});
