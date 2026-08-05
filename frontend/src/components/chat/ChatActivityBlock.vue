<template>
    <q-expansion-item
        dense
        switch-toggle-side
        :default-opened="defaultOpened"
        class="activity-block"
        header-class="activity-block-header"
        :style="activityStyle"
    >
        <template #header>
            <q-item-section avatar class="activity-icon">
                <q-icon :name="icon" size="18px" />
            </q-item-section>
            <q-item-section>
                <q-item-label class="activity-title">{{ title }}</q-item-label>
                <q-item-label caption class="activity-summary">{{ summary }}</q-item-label>
            </q-item-section>
            <q-item-section
                v-if="status === 'running' || status === 'failed'"
                side
                class="activity-status"
            >
                <q-spinner-dots v-if="status === 'running'" size="18px" />
                <q-icon v-else-if="status === 'failed'" name="error_outline" size="18px" />
            </q-item-section>
        </template>

        <div class="activity-content">
            <template v-if="mode === 'visual-and-raw'">
                <q-tabs
                    v-model="activeTab"
                    dense
                    no-caps
                    align="left"
                    narrow-indicator
                    class="activity-tabs"
                >
                    <q-tab name="visualization" :label="t('chat.activities.tabs.visualization')" />
                    <q-tab name="raw" :label="t('chat.activities.tabs.raw')" />
                </q-tabs>
                <q-tab-panels v-model="activeTab" class="activity-panels">
                    <q-tab-panel name="visualization" class="activity-panel">
                        <slot name="visualization" />
                    </q-tab-panel>
                    <q-tab-panel name="raw" class="activity-panel">
                        <slot name="raw" />
                    </q-tab-panel>
                </q-tab-panels>
            </template>
            <slot v-else name="raw" />
        </div>
    </q-expansion-item>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ToolCallStatus } from 'src/utils/model';

const props = defineProps<{
    title: string;
    summary: string;
    icon: string;
    color: string;
    mode: 'visual-and-raw' | 'raw-only';
    status?: ToolCallStatus | undefined;
    defaultOpened?: boolean;
}>();

const { t } = useI18n();
const activeTab = ref<'visualization' | 'raw'>('visualization');
const activityStyle = computed(() => ({ '--activity-color': props.color }));
</script>

<style scoped lang="scss">
.activity-block {
    border-left: 3px solid var(--activity-color);
    color: #475467;
    margin-bottom: 8px;
    max-width: 100%;
}

.activity-block :deep(.q-item) {
    min-height: 38px;
    padding: 0 6px;
}

.activity-block :deep(.q-item__section--avatar) {
    min-width: 26px;
    padding-right: 8px;
}

.activity-icon,
.activity-status {
    color: var(--activity-color);
}

.activity-title {
    font-size: 12px;
    font-weight: 650;
}

.activity-summary {
    color: #667085;
    font-size: 11px;
    font-weight: 500;
}

.activity-content {
    font-size: 13px;
    line-height: 1.45;
    min-width: 0;
    padding: 4px 8px 10px 38px;
    word-break: break-word;
}

.activity-tabs {
    color: #667085;
    margin-bottom: 8px;
    min-height: 30px;
}

.activity-tabs :deep(.q-tab) {
    min-height: 30px;
    padding: 0 12px;
}

.activity-tabs :deep(.q-tab--active) {
    color: var(--activity-color);
}

.activity-panels {
    background: transparent;
}

.activity-panel {
    padding: 0;
}
</style>
