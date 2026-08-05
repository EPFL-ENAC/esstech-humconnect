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
            <div class="expert-answer" :style="expertStyle">
                <div v-if="prompt || systemPrompt" class="expert-context">
                    <section v-if="prompt" class="expert-prompt">
                        <h4>{{ t('chat.activities.expert.question') }}</h4>
                        <p>{{ prompt }}</p>
                    </section>
                    <section v-if="systemPrompt" class="expert-prompt">
                        <h4>{{ t('chat.activities.expert.systemPrompt') }}</h4>
                        <p>{{ systemPrompt }}</p>
                    </section>
                </div>

                <div v-if="payload.status === 'running'" class="expert-loading">
                    <q-spinner-dots size="22px" />
                </div>
                <div v-else-if="payload.answer === ''" class="expert-empty">
                    <q-icon name="speaker_notes_off" size="20px" />
                    <span>{{ t('chat.activities.expert.emptyAnswer') }}</span>
                </div>
                <ChatMarkdownContent
                    v-else-if="payload.answer !== null"
                    class="expert-response"
                    :content="payload.answer"
                />
            </div>
        </template>

        <template #raw>
            <ToolCallRawContent :payload="payload" />
        </template>
    </ChatActivityBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ToolCallPayload } from 'src/utils/model';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ChatMarkdownContent from './ChatMarkdownContent.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';

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
    payload: ToolCallPayload;
}>();

const { t } = useI18n();
const presentation = computed(
    () => EXPERT_PRESENTATIONS[props.payload.tool_name] ?? DEFAULT_PRESENTATION,
);
const prompt = computed(() => stringArgument('prompt'));
const systemPrompt = computed(() => stringArgument('system_prompt'));
const expertStyle = computed(() => ({ '--expert-color': presentation.value.color }));
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

function stringArgument(name: string): string {
    const value = props.payload.arguments?.[name];
    return typeof value === 'string' ? value.trim() : '';
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
.expert-answer {
    --expert-color: #667085;
}

.expert-context {
    display: grid;
    gap: 6px;
    margin-bottom: 12px;
}

.expert-prompt {
    background: #f8fafc;
    border-left: 2px solid var(--expert-color);
    border-radius: 0 6px 6px 0;
    padding: 6px 8px;
}

.expert-prompt h4 {
    color: var(--expert-color);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.03em;
    line-height: 1.2;
    margin: 0 0 2px;
    text-transform: uppercase;
}

.expert-prompt p {
    color: #344054;
    font-size: 12px;
    margin: 0;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}

.expert-loading,
.expert-empty {
    align-items: center;
    color: var(--expert-color);
    display: flex;
    gap: 7px;
    min-height: 48px;
}

.expert-empty {
    color: #667085;
}

.expert-response {
    border-top: 1px solid #eaecf0;
    padding-top: 10px;
}
</style>
