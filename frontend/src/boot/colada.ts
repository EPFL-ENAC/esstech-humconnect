import { PiniaColada } from '@pinia/colada';
import { defineBoot } from '#q-app/wrappers';

export default defineBoot(({ app }) => {
    app.use(PiniaColada, {
        queryOptions: {
            staleTime: 1000 * 60 * 5, // 5 minutes
            gcTime: 1000 * 60 * 30, // 30 minutes
        },
    });
});
