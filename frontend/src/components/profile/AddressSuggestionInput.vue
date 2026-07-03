<template>
    <q-input
        :model-value="centerAddress || ''"
        outlined
        :disable="disabled"
        :label="label"
        :loading="searching"
        :placeholder="placeholder"
        @keyup.enter.prevent="searchSuggestionsImmediately"
        @update:model-value="updateAddress"
    >
        <template #append>
            <q-btn
                dense
                flat
                round
                icon="search"
                :disable="disabled || !canSearch"
                :loading="searching"
                @click.stop.prevent="searchSuggestionsImmediately"
            >
                <q-tooltip>{{ searchLabel }}</q-tooltip>
            </q-btn>
        </template>

        <q-menu v-model="showSuggestions" no-focus no-parent-event>
            <q-list class="suggestion-list">
                <q-item
                    v-for="suggestion in suggestions"
                    :key="suggestion.id"
                    v-close-popup
                    clickable
                    @click="selectSuggestion(suggestion)"
                >
                    <q-item-section>
                        <q-item-label>{{ suggestion.address }}</q-item-label>
                        <q-item-label caption lines="2">
                            {{ suggestion.display_name }}
                        </q-item-label>
                    </q-item-section>
                </q-item>

                <q-item v-if="suggestions.length === 0">
                    <q-item-section class="text-grey-7">
                        {{ noResultsLabel }}
                    </q-item-section>
                </q-item>
            </q-list>
        </q-menu>
    </q-input>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useDebouncedAction } from 'src/composables/useDebouncedAction';
import { searchAddressSuggestions } from 'src/utils/profileApi';
import type { AddressSuggestion, UserProfileCoordinates } from 'src/utils/model';

defineProps<{
    disabled: boolean;
    label: string;
    noResultsLabel: string;
    placeholder: string;
    searchLabel: string;
}>();

const centerAddress = defineModel<string | null>('centerAddress', { required: true });
const centerCoordinates = defineModel<UserProfileCoordinates | null>('centerCoordinates', {
    required: true,
});

const searching = ref(false);
const showSuggestions = ref(false);
const suggestions = ref<AddressSuggestion[]>([]);
let searchGeneration = 0;

const canSearch = computed(() => (centerAddress.value?.trim().length || 0) >= 3);
const {
    cancel: cancelSearchSuggestions,
    run: scheduleSearchSuggestions,
    runImmediately: searchSuggestionsImmediately,
} = useDebouncedAction(searchSuggestions, 250);

function updateAddress(value: string | number | null) {
    const address = String(value ?? '');
    centerAddress.value = address;
    centerCoordinates.value = null;
    searchGeneration += 1;
    showSuggestions.value = false;
    suggestions.value = [];

    if (canSearch.value) {
        scheduleSearchSuggestions();
    } else {
        cancelSearchSuggestions();
        searching.value = false;
    }
}

async function searchSuggestions() {
    const query = centerAddress.value?.trim() || '';
    if (query.length < 3) {
        return;
    }

    const generation = searchGeneration + 1;
    searchGeneration = generation;
    searching.value = true;
    showSuggestions.value = false;
    suggestions.value = [];

    try {
        const response = await searchAddressSuggestions(query);
        if (generation !== searchGeneration) {
            return;
        }
        suggestions.value = response.suggestions;
    } finally {
        if (generation === searchGeneration) {
            searching.value = false;
            showSuggestions.value = true;
        }
    }
}

function selectSuggestion(suggestion: AddressSuggestion) {
    cancelSearchSuggestions();
    searchGeneration += 1;
    centerAddress.value = suggestion.address;
    centerCoordinates.value = {
        latitude: suggestion.latitude,
        longitude: suggestion.longitude,
    };
    searching.value = false;
    showSuggestions.value = false;
}
</script>

<style scoped lang="scss">
.suggestion-list {
    max-width: min(560px, 90vw);
    min-width: min(420px, 90vw);
}
</style>
