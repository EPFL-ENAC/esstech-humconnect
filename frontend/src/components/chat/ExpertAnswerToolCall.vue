<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        :icon="presentation.icon"
        :color="presentation.color"
        :mode="mode"
        :status="payload.status"
        default-opened
    >
        <template #visualization>
            <ToolCallVisualizationSkeleton
                :loading="payload.status === 'running'"
                :accent-color="presentation.color"
                :query="visualizationQuery"
                :filters="visualizationFilters"
                :results-summary="visualizationResultsSummary"
                :empty-state="visualizationEmptyState"
            >
                <template #results>
                    <ChatMarkdownContent
                        v-if="payload.answer"
                        class="expert-response"
                        :content="payload.answer"
                    />
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
import type { ExpertAnswerToolCallPayload } from './toolCallSchemas';

interface ExpertPresentation {
    icon: string;
    color: string;
}

const EXPERT_PRESENTATIONS: Record<string, ExpertPresentation> = {
    ask_meditron: {
        icon: 'medical_services',
        color: '#0E9384',
    },
    ask_legitron: {
        icon: 'gavel',
        color: '#7F56D9',
    },
};

const DEFAULT_PRESENTATION: ExpertPresentation = {
    icon: 'forum',
    color: '#667085',
};

const props = defineProps<{
    payload: ExpertAnswerToolCallPayload;
}>();

const { t } = useI18n();
const presentation = computed(
    () => EXPERT_PRESENTATIONS[props.payload.tool_name] ?? DEFAULT_PRESENTATION,
);
const prompt = computed(() => props.payload.arguments.prompt);
const systemPrompt = computed(() => props.payload.arguments.system_prompt?.trim() ?? '');
const visualizationQuery = computed(() => ({
    label: t('chat.activities.expert.question'),
    value: prompt.value,
    icon: 'help_outline',
}));
const visualizationFilters = computed(() =>
    systemPrompt.value
        ? [
              {
                  icon: 'tune',
                  label: t('chat.activities.expert.systemPrompt'),
                  value: systemPrompt.value,
              },
          ]
        : [],
);
const visualizationResultsSummary = computed(() =>
    props.payload.status === 'finished' && props.payload.answer !== null
        ? localizedCharacterCount(props.payload.answer)
        : undefined,
);
const visualizationEmptyState = computed(() =>
    props.payload.status === 'finished' && props.payload.answer === ''
        ? {
              icon: 'speaker_notes_off',
              message: t('chat.activities.expert.emptyAnswer'),
          }
        : null,
);
const mode = computed(() => {
    if (props.payload.status === 'running') {
        return 'visual-and-raw';
    }

    if (props.payload.status === 'finished' && props.payload.answer !== null) {
        return 'visual-and-raw';
    }

    return 'raw-only';
});

const summary = computed(() => {
    const promptSummary = truncateUnicode(prompt.value, 60);
    const suffix = summarySuffix();

    if (!promptSummary) {
        return suffix;
    }

    return `${promptSummary} · ${suffix}`;
});

function summarySuffix(): string {
    if (props.payload.status === 'running') {
        return t('chat.activities.status.running');
    }

    if (props.payload.status === 'failed') {
        return t('chat.activities.status.failed');
    }

    return localizedCharacterCount(props.payload.answer ?? '');
}

function truncateUnicode(value: string, maxLength: number): string {
    const characters = Array.from(value);
    if (characters.length <= maxLength) {
        return value;
    }

    return `${characters.slice(0, maxLength - 1).join('')}…`;
}

function localizedCharacterCount(value: string): string {
    const count = Array.from(value).length;
    return t(count === 1 ? 'chat.activities.character' : 'chat.activities.characters', {
        count,
    });
}
</script>

<style scoped lang="scss">
.expert-response {
    min-width: 0;
}
</style>
