<template>
    <div class="signin-page">
        <section class="signin-panel">
            <h1>{{ t('auth.signinTitle') }}</h1>
            <p>{{ t('auth.signinSubtitle') }}</p>
            <q-btn
                color="primary"
                icon="login"
                :label="t('auth.signin')"
                :loading="loading"
                @click="signin"
            />
        </section>
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useAuthStore } from 'src/stores/auth';

const route = useRoute();
const { t } = useI18n();
const authStore = useAuthStore();
const loading = ref(false);

async function signin() {
    loading.value = true;
    try {
        await authStore.keycloak.login({
            redirectUri: `${window.location.origin}${window.location.pathname}#${String(
                route.query.redirect || '/',
            )}`,
        });
    } finally {
        loading.value = false;
    }
}
</script>

<style scoped lang="scss">
.signin-page {
    align-items: center;
    display: flex;
    justify-content: center;
    min-height: 100vh;
    padding: 24px;
}

.signin-panel {
    max-width: 420px;
    text-align: center;
}

h1 {
    font-size: 32px;
    line-height: 1.2;
    margin: 0 0 8px;
}

p {
    color: #667085;
    margin: 0 0 24px;
}
</style>
