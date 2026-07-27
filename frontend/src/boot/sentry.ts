import { defineBoot } from '#q-app/wrappers';
import * as Sentry from '@sentry/vue';

interface CustomWindow extends Window {
    env: {
        SENTRY_ENVIRONMENT?: string;
        SENTRY_RATE?: string;
    };
}

export default defineBoot(({ app }) => {
    const appEnv = (window as unknown as CustomWindow).env;

    Sentry.init({
        app,
        dsn: 'https://0351f1cad07e4a03a82904108ffde148@enac-it-glitchtip.epfl.ch/3',
        environment: appEnv.SENTRY_ENVIRONMENT ?? 'prod',
        tracesSampleRate: parseFloat(appEnv.SENTRY_RATE ?? '1.00'),
    });
});
