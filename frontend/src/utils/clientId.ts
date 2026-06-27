const CLIENT_ID_KEY = 'humconnect.clientId';

export function getClientId(): string {
    const existingClientId = window.localStorage.getItem(CLIENT_ID_KEY);
    if (existingClientId) {
        return existingClientId;
    }

    const clientId = window.crypto.randomUUID();
    window.localStorage.setItem(CLIENT_ID_KEY, clientId);
    return clientId;
}
