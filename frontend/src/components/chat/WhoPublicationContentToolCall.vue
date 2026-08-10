<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="menu_book"
        :color="toolColor"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                :accent-color="toolColor"
                :query="visualizationQuery"
                :warnings="result?.warnings"
                :results-summary="result ? '1' : undefined"
            >
                <template #results>
                    <ChatCardGallery v-if="result">
                        <ToolCardItem
                            :href="result.source_url"
                            :color="toolColor"
                            :eyebrow="t('chat.activities.whoPublicationContent.provider')"
                            :title="result.title"
                            :extra-info="publicationExtraInfo"
                        >
                            <template #content>
                                <div class="open-publication">
                                    {{ t('chat.activities.whoPublicationContent.openPublication') }}
                                    <q-icon name="arrow_forward" />
                                </div>
                            </template>
                        </ToolCardItem>
                    </ChatCardGallery>
                </template>
            </ToolCallVisualizationSkeleton>
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatCardGallery from './ChatCardGallery.vue';
import ToolCardItem from './ToolCardItem.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { WhoPublicationContentToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: WhoPublicationContentToolCallPayload;
}>();

const toolColor = '#087e8b';
const { t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() => ({
    label: t('chat.activities.whoPublicationContent.publicationId'),
    value: props.payload.arguments.item_id,
    icon: 'fingerprint',
}));
const truncatedCount = computed(
    () => result.value?.documents.filter((document) => document.truncated).length ?? 0,
);
const documentCountLabel = computed(() => {
    const count = result.value?.documents.length ?? 0;
    return t('chat.activities.whoPublicationContent.document', count);
});
const truncatedCountLabel = computed(() =>
    t('chat.activities.whoPublicationContent.truncatedDocument', truncatedCount.value),
);
const publicationExtraInfo = computed(() => {
    const info = [{ icon: 'description', value: documentCountLabel.value }];
    if (truncatedCount.value) {
        info.push({ icon: 'content_cut', value: truncatedCountLabel.value });
    }
    return info;
});
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.whoPublicationContent.loading');
    }

    if (result.value) {
        const count = result.value.documents.length;
        return t('chat.activities.whoPublicationContent.readyDocument', count);
    }

    return t(`chat.activities.status.${props.payload.status}`);
});
</script>

<style scoped lang="scss">
.open-publication {
    align-items: center;
    color: #087e8b;
    display: flex;
    font-size: 11px;
    font-weight: 650;
    gap: 4px;
}
</style>
