<template>
    <div class="raw-content">
        <section class="raw-section">
            <h4>{{ t('chat.activities.raw.input') }}</h4>
            <pre>{{ formattedArguments }}</pre>
        </section>
        <section class="raw-section">
            <h4>{{ t('chat.activities.raw.output') }}</h4>
            <pre v-if="rawOutput !== null" :class="{ 'raw-error': payload.status === 'failed' }">{{
                rawOutput
            }}</pre>
            <div v-else class="raw-waiting">
                <q-spinner-dots v-if="payload.status === 'running'" size="18px" />
                <span>{{
                    t(
                        payload.status === 'running'
                            ? 'chat.activities.raw.waiting'
                            : 'chat.activities.raw.noOutput',
                    )
                }}</span>
            </div>
        </section>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ToolCallDisplayPayload } from './toolCallSchemas';
import { prettyPrintJson } from 'src/utils/text';

const props = defineProps<{
    payload: ToolCallDisplayPayload;
}>();

const { t } = useI18n();

const formattedArguments = computed(() => formatRawValue(props.payload.arguments) ?? 'null');
const rawOutput = computed(() => formatRawValue(props.payload.answer ?? props.payload.error));

function formatRawValue(value: unknown): string | null {
    if (value === null) {
        return null;
    }

    return typeof value === 'string' ? value : prettyPrintJson(value);
}
</script>

<style scoped lang="scss">
.raw-section + .raw-section {
    margin-top: 12px;
}

.raw-section h4 {
    color: #667085;
    font-size: 11px;
    font-weight: 650;
    letter-spacing: 0.03em;
    margin: 0 0 4px;
    text-transform: uppercase;
}

.raw-section pre {
    background: #f8fafc;
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-radius: 6px;
    font-family: 'Roboto Mono', monospace;
    font-size: 12px;
    margin: 0;
    max-height: 360px;
    overflow: auto;
    padding: 8px;
    white-space: pre-wrap;
}

.raw-section pre.raw-error {
    background: #fff6f5;
    color: #b42318;
}

.raw-waiting {
    align-items: center;
    color: #667085;
    display: flex;
    gap: 6px;
}
</style>
