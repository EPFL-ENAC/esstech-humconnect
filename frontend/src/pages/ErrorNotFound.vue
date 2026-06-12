<template>
  <div class="fullscreen text-primary text-center q-pa-md flex flex-center">
    <div>
      <div style="font-size: 30vh">404</div>

      <div class="text-h2">{{ t('notFoundMessage') }}</div>

      <q-btn
        class="q-mt-xl"
        color="primary"
        text-color="white"
        unelevated
        to="/"
        :label="t('goHome')"
        no-caps
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
</script>
