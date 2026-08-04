<template>
    <ChatActivityBlock
        :title="title"
        :summary="summary"
        icon="construction"
        color="#667085"
        mode="raw-only"
        :status="payload?.status ?? 'running'"
        default-opened
    >
        <template #raw>
            <ToolCallRawContent v-if="payload" :payload="payload" />
            <div v-else class="tool-call-loading">
                <q-spinner-dots size="22px" color="grey-7" />
            </div>
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ToolCallPayload } from 'src/utils/model';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';

const props = defineProps<{
    payload: ToolCallPayload | null;
}>();

const { t } = useI18n();
const title = computed(() => props.payload?.tool_label ?? t('chat.activities.toolCall'));
const summary = computed(() => t(`chat.activities.status.${props.payload?.status ?? 'running'}`));
</script>

<style scoped lang="scss">
.tool-call-loading {
    align-items: center;
    color: #667085;
    display: flex;
    min-height: 48px;
}
</style>
