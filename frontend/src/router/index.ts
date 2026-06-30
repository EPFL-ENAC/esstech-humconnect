import { defineRouter } from '#q-app/wrappers';
import { createMemoryHistory, createRouter, createWebHistory } from 'vue-router';
import routes from './routes';
import { useAuthStore } from 'src/stores/auth';

/*
 * If not building with SSR mode, you can
 * directly export the Router instantiation;
 *
 * The function below can be async too; either use
 * async/await or return a Promise which resolves
 * with the Router instance.
 */

export default defineRouter(function ({ store }) {
    const createHistory = process.env.SERVER ? createMemoryHistory : createWebHistory;

    const Router = createRouter({
        scrollBehavior: () => ({ left: 0, top: 0 }),
        routes,

        // Leave this as is and make changes in quasar.conf.js instead!
        // quasar.conf.js -> build -> vueRouterMode
        // quasar.conf.js -> build -> publicPath
        history: createHistory(process.env.VUE_ROUTER_BASE),
    });

    Router.beforeEach(async (to) => {
        const authStore = useAuthStore(store);
        await authStore.init();

        if (to.meta.public) {
            if (authStore.isAuthenticated && to.path === '/signin') {
                return '/';
            }
            return true;
        }

        if (!authStore.isAuthenticated) {
            return {
                path: '/signin',
                query: { redirect: to.fullPath },
            };
        }

        if (to.meta.requiresAdmin && !authStore.isAdmin) {
            return '/';
        }

        return true;
    });

    return Router;
});
