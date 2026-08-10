<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="health_and_safety"
        color="#087e8b"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                accent-color="#087e8b"
                :query="visualizationQuery"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #results>
                    <ChatCardGallery v-if="result?.results.length">
                        <ToolCardItem
                            v-for="publication in result.results"
                            :key="publication.item_id"
                            :href="publication.source_url"
                            color="#087e8b"
                            :eyebrow="t('chat.activities.whoPublications.provider')"
                            :title="publication.title"
                            :extra-info="publicationExtraInfo(publication)"
                        >
                            <template #content>
                                <p v-if="publication.abstract" class="abstract">
                                    {{ publication.abstract }}
                                </p>
                                <p v-else class="abstract abstract-empty">
                                    {{ t('chat.activities.whoPublications.noAbstract') }}
                                </p>
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
import type { WhoPublication, WhoPublicationSearchToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: WhoPublicationSearchToolCallPayload;
}>();

const { locale, t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() => ({
    label: t('chat.activities.whoPublications.query'),
    value: result.value?.query ?? props.payload.arguments.query,
    icon: 'search',
}));
const visualizationResultsSummary = computed(() =>
    result.value
        ? t('chat.activities.whoPublications.resultSummary', {
              total: result.value.total,
              shown: result.value.results.length,
          })
        : undefined,
);
const visualizationEmptyState = computed(() =>
    result.value && !result.value.results.length
        ? {
              icon: 'find_in_page',
              message: t('chat.activities.whoPublications.noResults'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.whoPublications.searching', {
            query: props.payload.arguments.query,
        });
    }

    if (result.value) {
        const count = result.value.results.length;
        return t(
            count === 1
                ? 'chat.activities.whoPublications.result'
                : 'chat.activities.whoPublications.results',
            { count },
        );
    }

    return t(`chat.activities.status.${props.payload.status}`);
});

function formatDate(value: string | null): string {
    if (!value) {
        return t('chat.activities.whoPublications.unknownDate');
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium' }).format(date);
}

function formatList(values: string[]): string {
    return values.length ? values.join(' · ') : t('chat.activities.whoPublications.notAvailable');
}

function publicationExtraInfo(publication: WhoPublication) {
    return [
        { icon: 'calendar_today', value: formatDate(publication.published_date) },
        { icon: 'person', value: formatList(publication.authors) },
        { icon: 'description', value: formatList(publication.document_types) },
        { icon: 'translate', value: formatList(publication.languages) },
        { icon: 'sell', value: formatList(publication.subjects) },
    ];
}
</script>

<style scoped lang="scss">
.abstract {
    color: #475467;
    display: -webkit-box;
    font-size: 12px;
    -webkit-line-clamp: 4;
    line-height: 1.45;
    margin: 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
}

.abstract-empty {
    color: #98a2b3;
    font-style: italic;
}
</style>
