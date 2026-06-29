<template>
    <q-layout view="hHh LpR lFf">
        <q-header>
            <q-toolbar class="q-px-md">
                EPFL
                <q-toolbar-title> {{ t('appTitle') }} </q-toolbar-title>
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

                <q-item v-ripple clickable to="/dashboard">
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
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const leftDrawerOpen = ref(true);
</script>
