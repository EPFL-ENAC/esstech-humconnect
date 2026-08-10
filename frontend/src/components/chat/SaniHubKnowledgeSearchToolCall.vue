<template>
    <ChatActivityBlock
        :title="`SaniHub: ${payload.tool_label}`"
        :summary="summary"
        icon="sanitizer"
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
                    <ChatCardGallery v-if="result?.results.length">
                        <ToolCardItem
                            v-for="item in result.results"
                            :key="`${item.REF_ID}-${item.pageNum ?? 'document'}`"
                            :href="item.url"
                            :color="toolColor"
                            :eyebrow="t('chat.activities.sanihub.provider')"
                            :title="item.title"
                            :extra-info="resultExtraInfo(item)"
                        >
                            <template #content>
                                <p v-if="item.content" class="result-excerpt">
                                    {{ markdownToText(item.content) }}
                                </p>
                                <p v-else class="result-excerpt result-excerpt-empty">
                                    {{ t('chat.activities.sanihub.noExcerpt') }}
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
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import ToolCardItem from './ToolCardItem.vue';
import type {
    SaniHubKnowledgeResult,
    SaniHubKnowledgeSearchToolCallPayload,
} from './toolCallSchemas';

const props = defineProps<{
    payload: SaniHubKnowledgeSearchToolCallPayload;
}>();

type SaniHubTopic = SaniHubKnowledgeSearchToolCallPayload['arguments']['topics'][number];

const sanihubTopicTranslationKeys: Record<SaniHubTopic, string> = {
    Preparedness: 'preparedness',
    'Needs Assessment': 'needsAssessment',
    'Strategic Planning': 'strategicPlanning',
    'Resource Mobilisation': 'resourceMobilisation',
    'Implementation Monitoring': 'implementationMonitoring',
    'Review Evaluation': 'reviewEvaluation',
    'Sanitation Technologies': 'sanitationTechnologies',
    'Technology Selection': 'technologySelection',
    'Faecal Sludge': 'faecalSludge',
    'Sanitation Software': 'sanitationSoftware',
    'Wider Systems': 'widerSystems',
    'Cross-Cutting Issues': 'crossCuttingIssues',
    'Coordination Sectors': 'coordinationSectors',
    Accountability: 'accountability',
    'Capacity Development': 'capacityDevelopment',
    'Research Innovation': 'researchInnovation',
    'Knowledge Management': 'knowledgeManagement',
    'Case Studies': 'caseStudies',
    'Challenging Contexts': 'challengingContexts',
    'Disaster Scenarios': 'disasterScenarios',
    'Climate Challenges': 'climateChallenges',
    'Ground Conditions': 'groundConditions',
};

const toolColor = '#147d64';
const { t } = useI18n();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() => ({
    label: t('chat.activities.sanihub.searchRequest'),
    value: props.payload.arguments.userQuery,
    icon: 'search',
}));
const visualizationFilters = computed(() => {
    const filters = [
        {
            icon: 'manage_search',
            label: t('chat.activities.sanihub.queryVariations'),
            value: props.payload.arguments.queries.join(' · '),
        },
    ];

    if (props.payload.arguments.topics.length) {
        filters.push({
            icon: 'sell',
            label: t('chat.activities.sanihub.topics'),
            value: props.payload.arguments.topics.map(localizedTopic).join(' · '),
        });
    }

    if (props.payload.arguments.locations.length) {
        filters.push({
            icon: 'public',
            label: t('chat.activities.sanihub.locations'),
            value: props.payload.arguments.locations.join(' · '),
        });
    }

    if (props.payload.arguments.documentListOnly) {
        filters.push({
            icon: 'description',
            label: t('chat.activities.sanihub.mode'),
            value: t('chat.activities.sanihub.documentsOnly'),
        });
    }

    return filters;
});
const visualizationResultsSummary = computed(() =>
    result.value ? localizedResultCount(result.value.resultCount) : undefined,
);
const visualizationEmptyState = computed(() =>
    result.value && !result.value.results.length
        ? {
              icon: 'find_in_page',
              message: t('chat.activities.sanihub.noResults'),
          }
        : null,
);
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.sanihub.searching');
    }

    if (result.value) {
        return localizedResultCount(result.value.resultCount);
    }

    return t(`chat.activities.status.${props.payload.status}`);
});

function localizedResultCount(count: number): string {
    return t(count === 1 ? 'chat.activities.sanihub.result' : 'chat.activities.sanihub.results', {
        count,
    });
}

function localizedTopic(topic: SaniHubTopic): string {
    return t(`chat.activities.sanihub.topicLabels.${sanihubTopicTranslationKeys[topic]}`);
}

function resultExtraInfo(item: SaniHubKnowledgeResult) {
    const info = [{ icon: 'fingerprint', value: item.documentId }];
    if (item.pageNum !== undefined) {
        info.unshift({
            icon: 'article',
            value: t('chat.activities.sanihub.page', { page: item.pageNum }),
        });
    }
    return info;
}

function markdownToText(value: string): string {
    return value
        .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
        .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
        .replace(/^[#>*_`\s-]+/gm, '')
        .replace(/[*_`]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}
</script>

<style scoped lang="scss">
.result-excerpt {
    color: #475467;
    display: -webkit-box;
    font-size: 12px;
    -webkit-line-clamp: 5;
    line-height: 1.45;
    margin: 0;
    overflow: hidden;
    -webkit-box-orient: vertical;
}

.result-excerpt-empty {
    color: #98a2b3;
    font-style: italic;
}
</style>
