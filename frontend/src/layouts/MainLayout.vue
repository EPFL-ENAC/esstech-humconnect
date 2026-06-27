<template>
    <q-layout view="hHh LpR lFf">
        <q-header>
            <q-toolbar class="q-px-md">
                EPFL
                <q-toolbar-title> {{ t('appTitle') }} </q-toolbar-title>
            </q-toolbar>
        </q-header>

        <q-drawer v-model="leftDrawerOpen" :breakpoint="0" :width="314" bordered> </q-drawer>

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
