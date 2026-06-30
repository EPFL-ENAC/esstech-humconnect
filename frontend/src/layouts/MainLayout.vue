<template>
    <q-layout view="hHh LpR lFf">
        <q-header>
            <q-toolbar class="q-px-md">
                EPFL
                <q-toolbar-title> {{ t('appTitle') }} </q-toolbar-title>
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

                <q-item v-if="authStore.isAdmin" v-ripple clickable to="/dashboard">
                    <q-item-section avatar>
                        <q-icon name="dashboard" />
                    </q-item-section>
                    <q-item-section>{{ t('navigation.dashboard') }}</q-item-section>
                </q-item>
            </q-list>
        </q-drawer>

        <q-page-container>
            <router-view />
        </q-page-container>
    </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useAuthStore } from 'src/stores/auth';

const { t } = useI18n();
const router = useRouter();
const authStore = useAuthStore();
const leftDrawerOpen = ref(true);

async function logout() {
    await authStore.logout();
    await router.push('/signin');
}
</script>
