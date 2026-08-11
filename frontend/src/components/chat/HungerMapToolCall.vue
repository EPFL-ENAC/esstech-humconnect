<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="restaurant"
        color="#007dbc"
        mode="raw-only"
        :status="payload.status"
        default-opened
    >
        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import type { HungerMapToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: HungerMapToolCallPayload;
}>();

const { t } = useI18n();
const summary = computed(() => t(`chat.activities.status.${props.payload.status}`));
</script>
