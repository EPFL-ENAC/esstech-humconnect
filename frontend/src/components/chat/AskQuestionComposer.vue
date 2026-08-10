<template>
    <div class="ask-question-composer">
        <div class="question-text">
            <ChatMarkdownContent :content="question" />
        </div>

        <q-list v-if="possibleAnswers.length > 0" bordered separator class="answer-list">
            <q-item
                v-for="option in answerOptions"
                :key="option.value"
                v-ripple="!isDisabled"
                :clickable="!isDisabled"
                :active="selected === option.value"
                active-class="answer-option--active"
                class="answer-option"
                @click="selectOption(option.value)"
            >
                <q-item-section avatar>
                    <q-radio
                        v-model="selected"
                        :val="option.value"
                        color="primary"
                        :disable="isDisabled"
                    />
                </q-item-section>
                <q-item-section>
                    <div v-if="option.value === OTHER_VALUE" class="answer-option__other-row">
                        <q-item-label class="answer-option__label answer-option__other-label">
                            {{ option.label }}
                        </q-item-label>
                        <q-input
                            v-model="otherText"
                            outlined
                            dense
                            autogrow
                            :placeholder="t('chat.askQuestion.otherPlaceholder')"
                            :disable="isDisabled"
                            class="answer-option__other-input"
                            @update:model-value="onOtherInput"
                            @keydown.enter.prevent="handleSubmit"
                        />
                    </div>
                    <q-item-label v-else class="answer-option__label">
                        {{ option.label }}
                    </q-item-label>
                </q-item-section>
            </q-item>
        </q-list>

        <form
            class="answer-row"
            :class="{ 'with-input': hasFreeTextInput }"
            @submit.prevent="handleSubmit"
        >
            <q-input
                v-if="hasFreeTextInput"
                v-model="freeText"
                outlined
                dense
                autogrow
                :placeholder="t('chat.askQuestion.answerPlaceholder')"
                :disable="isDisabled"
                @keydown.enter.prevent="handleSubmit"
            />
            <q-btn
                round
                color="primary"
                icon="send"
                type="submit"
                :disable="!canSubmit"
                :loading="submitting"
                @click="handleSubmit"
            >
                <q-tooltip>{{ t('chat.send') }}</q-tooltip>
            </q-btn>
        </form>
    </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import ChatMarkdownContent from './ChatMarkdownContent.vue';

const OTHER_VALUE = '__other__';

const props = defineProps<{
    question: string;
    possibleAnswers: string[];
    submit: (content: string) => Promise<boolean>;
    disabled?: boolean;
}>();

const { t } = useI18n();
const selected = ref<string | null>(null);
const otherText = ref('');
const freeText = ref('');
const submitting = ref(false);

const isDisabled = computed(() => props.disabled || submitting.value);

const answerOptions = computed(() => [
    ...props.possibleAnswers.map((answer) => ({ label: answer, value: answer })),
    { label: t('chat.askQuestion.other'), value: OTHER_VALUE },
]);

const hasFreeTextInput = computed(() => props.possibleAnswers.length === 0);

const canSubmit = computed(() => {
    if (isDisabled.value) {
        return false;
    }
    if (props.possibleAnswers.length > 0) {
        if (selected.value === null) {
            return false;
        }
        if (selected.value === OTHER_VALUE) {
            return otherText.value.trim().length > 0;
        }
        return true;
    }
    return freeText.value.trim().length > 0;
});

function selectOption(value: string) {
    if (isDisabled.value) {
        return;
    }
    selected.value = value;
}

function onOtherInput() {
    if (isDisabled.value) {
        return;
    }
    selected.value = OTHER_VALUE;
}

async function handleSubmit() {
    if (!canSubmit.value || submitting.value) {
        return;
    }

    let content: string;
    if (props.possibleAnswers.length > 0) {
        if (selected.value === OTHER_VALUE) {
            content = otherText.value.trim();
        } else {
            content = selected.value as string;
        }
    } else {
        content = freeText.value.trim();
    }

    if (!content) {
        return;
    }

    submitting.value = true;
    try {
        const ok = await props.submit(content);
        if (ok) {
            selected.value = null;
            otherText.value = '';
            freeText.value = '';
        }
    } finally {
        submitting.value = false;
    }
}
</script>

<style scoped lang="scss">
.ask-question-composer {
    align-items: stretch;
    background: #f7f8fa;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
}

.question-text {
    background: #fff;
    border-left: 3px solid var(--q-primary, #2563eb);
    border-radius: 4px;
    font-weight: 500;
    padding: 8px 10px;
}

.answer-list {
    border-radius: 8px;
    overflow: hidden;
}

.answer-option {
    min-height: 52px;
    padding: 8px 12px;
    transition: background 0.15s ease;
}

.answer-option--active {
    background: rgba(255, 0, 0, 0.08);
    box-shadow: inset 3px 0 0 0 var(--q-primary, #ff0000);
}

.answer-option__label {
    font-weight: 500;
}

.answer-option--active .answer-option__label {
    font-weight: 600;
}

.answer-option__other-row {
    align-items: center;
    display: flex;
    gap: 10px;
    width: 100%;
}

.answer-option__other-label {
    flex: 0 0 auto;
    white-space: nowrap;
}

.answer-option__other-input {
    flex: 1 1 auto;
    margin-top: 0;
    min-width: 0;
}

.answer-row {
    align-items: flex-end;
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    width: 100%;
}

.answer-row.with-input {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
}
</style>
