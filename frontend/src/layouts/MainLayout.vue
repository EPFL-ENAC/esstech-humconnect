<template>
    <q-layout view="hHh LpR lFf">
        <q-header>
            <q-toolbar class="q-px-md">
                <q-img
                    src="/epfl.svg"
                    alt="EPFL logo"
                    class="logo q-mr-sm"
                    no-spinner
                    style="width: 96px"
                />
                <q-toolbar-title> {{ t('appTitle') }} </q-toolbar-title>
                <q-btn-dropdown
                    flat
                    dense
                    no-caps
                    icon="language"
                    :label="locale === 'fr' ? 'FR' : 'EN'"
                    :aria-label="t('language.label')"
                >
                    <q-list>
                        <q-item
                            v-for="option in localeOptions"
                            :key="option.value"
                            v-close-popup
                            clickable
                            @click="selectLocale(option.value)"
                        >
                            <q-item-section>{{ t(option.labelKey) }}</q-item-section>
                        </q-item>
                    </q-list>
                </q-btn-dropdown>
                <q-btn flat round icon="logout" @click="logout">
                    <q-tooltip>{{ t('auth.logout') }}</q-tooltip>
                </q-btn>
            </q-toolbar>
        </q-header>

        <q-drawer v-model="leftDrawerOpen" :breakpoint="0" :width="314" bordered>
            <q-list padding>
                <q-item v-ripple clickable to="/" exact>
                    <q-item-section avatar>
                        <q-icon name="chat" />
                    </q-item-section>
                    <q-item-section>{{ t('navigation.chats') }}</q-item-section>
                </q-item>

                <q-item v-ripple clickable to="/profile">
                    <q-item-section avatar>
                        <q-icon name="person" />
                    </q-item-section>
                    <q-item-section>{{ t('navigation.profile') }}</q-item-section>
                </q-item>

                <q-item v-if="authStore.isAdmin" v-ripple clickable to="/dashboard">
                    <q-item-section avatar>
                        <q-icon name="dashboard" />
                    </q-item-section>
                    <q-item-section>{{ t('navigation.dashboard') }}</q-item-section>
                </q-item>
            </q-list>
        </q-drawer>

        <q-page-container>
            <q-banner v-if="showDisclaimer" class="bg-amber-2 text-brown-10">
                <template #avatar>
                    <q-icon name="warning_amber" />
                </template>

                {{ t('disclaimer.message') }}

                <template #action>
                    <q-btn
                        flat
                        round
                        dense
                        icon="close"
                        :aria-label="t('disclaimer.dismiss')"
                        @click="showDisclaimer = false"
                    />
                </template>
            </q-banner>
            <router-view />
        </q-page-container>
    </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useAuthStore } from 'src/stores/auth';

type AppLocale = 'en-US' | 'fr';

const localeOptions: { value: AppLocale; labelKey: string }[] = [
    { value: 'en-US', labelKey: 'language.english' },
    { value: 'fr', labelKey: 'language.french' },
];

const { locale, t } = useI18n();
const router = useRouter();
const authStore = useAuthStore();
const leftDrawerOpen = ref(true);
const showDisclaimer = ref(true);

function selectLocale(nextLocale: AppLocale): void {
    locale.value = nextLocale;
    localStorage.setItem('app-locale', nextLocale);
}

async function logout() {
    await authStore.logout();
    await router.push('/signin');
}
</script>
