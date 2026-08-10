<template>
    <ChatActivityBlock
        :title="`SaniHub: ${payload.tool_label}`"
        :summary="summary"
        icon="library_books"
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
                :filters="visualizationFilters"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #results>
                    <div v-if="result?.pages.length" class="document-content">
                        <header class="document-heading">
                            <span>{{ t('chat.activities.sanihub.document') }}</span>
                            <h5>{{ result.title }}</h5>
                        </header>
                        <section
                            v-for="page in result.pages"
                            :key="page.pageNum"
                            class="document-page"
                        >
                            <h6>{{ t('chat.activities.sanihub.page', { page: page.pageNum }) }}</h6>
                            <ChatMarkdownContent :content="page.content" />
                        </section>
                    </div>
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
import ChatMarkdownContent from './ChatMarkdownContent.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { SaniHubDocumentContentToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: SaniHubDocumentContentToolCallPayload;
}>();

const toolColor = '#147d64';
const { t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() => ({
    label: t('chat.activities.sanihub.documentId'),
    value: props.payload.arguments.documentId,
    icon: 'fingerprint',
}));
const visualizationFilters = computed(() => [
    {
        icon: 'article',
        label: t('chat.activities.sanihub.requestedPages'),
        value: props.payload.arguments.pages,
    },
]);
const visualizationResultsSummary = computed(() =>
    result.value ? localizedPageCount(result.value.pages.length) : undefined,
);
const visualizationEmptyState = computed(() =>
    result.value && !result.value.pages.length
        ? {
              icon: 'find_in_page',
              message: t('chat.activities.sanihub.noPages'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.sanihub.loadingDocument');
    }

    if (result.value) {
        return localizedPageCount(result.value.pages.length);
    }

    return t(`chat.activities.status.${props.payload.status}`);
});

function localizedPageCount(count: number): string {
    return t('chat.activities.sanihub.pageResult', count);
}
</script>

<style scoped lang="scss">
.document-content {
    min-width: 0;
}

.document-heading span {
    color: #147d64;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.document-heading h5 {
    color: #101828;
    font-size: 15px;
    line-height: 1.35;
    margin: 4px 0 12px;
}

.document-page {
    border-top: 1px solid #eaecf0;
    padding: 12px 0;
}

.document-page h6 {
    color: #147d64;
    font-size: 11px;
    font-weight: 700;
    margin: 0 0 8px;
    text-transform: uppercase;
}
</style>
