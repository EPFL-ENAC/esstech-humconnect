import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
    {
        path: '/',
        component: () => import('layouts/MainLayout.vue'),
        children: [
            { path: '', component: () => import('pages/IndexPage.vue') },
            { path: 'chat/:id', component: () => import('pages/ChatPage.vue') },
            {
                path: 'dashboard',
                component: () => import('pages/DashboardPage.vue'),
                meta: { requiresAdmin: true },
            },
        ],
    },
    {
        path: '/signin',
        component: () => import('pages/SigninPage.vue'),
        meta: { public: true },
    },

    // Always leave this as last one,
    // but you can also remove it
    {
        path: '/:catchAll(.*)*',
        component: () => import('pages/ErrorNotFound.vue'),
    },
];

export default routes;
