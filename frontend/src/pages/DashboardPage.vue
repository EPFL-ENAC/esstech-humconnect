<template>
    <q-page class="dashboard-page">
        <section class="dashboard-content">
            <div class="header-row">
                <div>
                    <h1>{{ t('dashboard.title') }}</h1>
                    <p>{{ t('dashboard.subtitle') }}</p>
                </div>

                <q-btn
                    outline
                    color="primary"
                    icon="refresh"
                    :label="t('dashboard.refresh')"
                    :loading="loading"
                    @click="loadEvents"
                />
            </div>

            <q-banner v-if="error" class="bg-red-1 text-red-9 q-mb-md" rounded>
                {{ error }}
            </q-banner>

            <q-card flat bordered class="filters-card">
                <q-card-section>
                    <h2 class="filters-title">{{ t('dashboard.filters.title') }}</h2>
                    <q-form class="filters-form" @submit.prevent="applyFilters">
                        <div class="filters-grid">
                            <q-input
                                v-model="draftFilters.keyword"
                                outlined
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.keyword')"
                            />
                            <q-select
                                v-model="draftFilters.tags"
                                outlined
                                multiple
                                use-chips
                                emit-value
                                map-options
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.tags')"
                                :options="tagOptions"
                            />
                            <q-select
                                v-model="draftFilters.affectedProfessionCategories"
                                outlined
                                multiple
                                use-chips
                                emit-value
                                map-options
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.affectedProfessions')"
                                :options="professionOptions"
                            />
                            <q-select
                                v-model="draftFilters.responseProfessionCategories"
                                outlined
                                multiple
                                use-chips
                                emit-value
                                map-options
                                clearable
                                :disable="loading"
                                :label="t('dashboard.filters.responseProfessions')"
                                :options="professionOptions"
                            />
                        </div>
                        <div class="filter-actions">
                            <q-btn
                                flat
                                color="primary"
                                :disable="loading"
                                :label="t('dashboard.filters.clear')"
                                @click="clearFilters"
                            />
                            <q-btn
                                color="primary"
                                icon="filter_alt"
                                type="submit"
                                :disable="loading"
                                :loading="loading"
                                :label="t('dashboard.filters.apply')"
                            />
                        </div>
                    </q-form>
                </q-card-section>
            </q-card>

            <q-list bordered separator class="event-list">
                <q-item v-if="loading">
                    <q-item-section>{{ t('dashboard.loading') }}</q-item-section>
                </q-item>

                <q-item v-else-if="events.length === 0">
                    <q-item-section>
                        {{
                            hasAppliedFilters ? t('dashboard.filteredEmpty') : t('dashboard.empty')
                        }}
                    </q-item-section>
                </q-item>

                <template v-else>
                    <q-expansion-item
                        v-for="event in events"
                        :key="event.id"
                        expand-separator
                        group="recorded-events"
                    >
                        <template #header>
                            <q-item-section>
                                <q-item-label class="event-title">{{
                                    event.event_name
                                }}</q-item-label>
                                <q-item-label caption>{{ event.original_text }}</q-item-label>
                            </q-item-section>
                            <q-item-section side class="event-meta">
                                <span>{{ formatEventDateRange(event) }}</span>
                            </q-item-section>
                        </template>

                        <div class="event-details">
                            <dl>
                                <div>
                                    <dt>{{ t('dashboard.fields.createdAt') }}</dt>
                                    <dd>{{ formatDate(event.created_at) }}</dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.eventStartDate') }}</dt>
                                    <dd>
                                        {{
                                            event.event_datetime
                                                ? formatDate(event.event_datetime)
                                                : '-'
                                        }}
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.startDateQuality') }}</dt>
                                    <dd>
                                        {{ event.event_date_granularity }} /
                                        {{ event.event_date_precision }}
                                    </dd>
                                </div>
                                <div v-if="event.event_end_datetime">
                                    <dt>{{ t('dashboard.fields.eventEndDate') }}</dt>
                                    <dd>{{ formatDate(event.event_end_datetime) }}</dd>
                                </div>
                                <div v-if="event.event_end_datetime">
                                    <dt>{{ t('dashboard.fields.endDateQuality') }}</dt>
                                    <dd>
                                        {{ event.event_end_date_granularity }} /
                                        {{ event.event_end_date_precision }}
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.location') }}</dt>
                                    <dd>{{ formatLocation(event.event_location) }}</dd>
                                </div>
                                <div v-if="event.event_location.continent">
                                    <dt>{{ t('dashboard.fields.continent') }}</dt>
                                    <dd>{{ continentLabel(event.event_location.continent) }}</dd>
                                </div>
                                <div v-if="event.event_location.country_code">
                                    <dt>{{ t('dashboard.fields.countryCode') }}</dt>
                                    <dd>{{ event.event_location.country_code }}</dd>
                                </div>
                                <div v-if="event.event_location.region">
                                    <dt>{{ t('dashboard.fields.region') }}</dt>
                                    <dd>{{ event.event_location.region }}</dd>
                                </div>
                                <div v-if="event.event_location.city">
                                    <dt>{{ t('dashboard.fields.city') }}</dt>
                                    <dd>{{ event.event_location.city }}</dd>
                                </div>
                                <div v-if="event.event_location.address">
                                    <dt>{{ t('dashboard.fields.address') }}</dt>
                                    <dd>{{ event.event_location.address }}</dd>
                                </div>
                                <div v-if="event.event_location.place_name">
                                    <dt>{{ t('dashboard.fields.placeName') }}</dt>
                                    <dd>{{ event.event_location.place_name }}</dd>
                                </div>
                                <div v-if="event.event_location.detail">
                                    <dt>{{ t('dashboard.fields.locationDetail') }}</dt>
                                    <dd>{{ event.event_location.detail }}</dd>
                                </div>
                                <div v-if="event.event_location.coordinates">
                                    <dt>{{ t('dashboard.fields.coordinates') }}</dt>
                                    <dd class="monospace">
                                        {{ formatCoordinates(event.event_location.coordinates) }}
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.severity') }}</dt>
                                    <dd>
                                        <q-chip dense color="red-2" text-color="red-10">
                                            {{ t('dashboard.severity.local') }}:
                                            {{ formatSeverity(event.local_severity) }}
                                        </q-chip>
                                        <q-chip dense color="orange-2" text-color="orange-10">
                                            {{ t('dashboard.severity.country') }}:
                                            {{ formatSeverity(event.country_severity) }}
                                        </q-chip>
                                        <q-chip dense color="purple-2" text-color="purple-10">
                                            {{ t('dashboard.severity.global') }}:
                                            {{ formatSeverity(event.global_severity) }}
                                        </q-chip>
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.tags') }}</dt>
                                    <dd>
                                        <q-chip
                                            v-for="tag in event.tags"
                                            :key="tag"
                                            dense
                                            color="primary"
                                            text-color="white"
                                        >
                                            {{ eventTagLabel(tag) }}
                                        </q-chip>
                                        <span v-if="event.tags.length === 0">-</span>
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.keywords') }}</dt>
                                    <dd>
                                        <q-chip
                                            v-for="keyword in event.keywords"
                                            :key="keyword"
                                            dense
                                            color="grey-4"
                                            text-color="grey-9"
                                        >
                                            {{ keyword }}
                                        </q-chip>
                                        <span v-if="event.keywords.length === 0">-</span>
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.affectedProfessions') }}</dt>
                                    <dd>
                                        <q-chip
                                            v-for="category in event.affected_profession_categories"
                                            :key="category"
                                            dense
                                            color="orange-2"
                                            text-color="orange-10"
                                        >
                                            {{ professionLabel(category) }}
                                        </q-chip>
                                        <span
                                            v-if="event.affected_profession_categories.length === 0"
                                        >
                                            -
                                        </span>
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.responseProfessions') }}</dt>
                                    <dd>
                                        <q-chip
                                            v-for="category in event.response_profession_categories"
                                            :key="category"
                                            dense
                                            color="green-2"
                                            text-color="green-10"
                                        >
                                            {{ professionLabel(category) }}
                                        </q-chip>
                                        <span
                                            v-if="event.response_profession_categories.length === 0"
                                        >
                                            -
                                        </span>
                                    </dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.chatId') }}</dt>
                                    <dd class="monospace">{{ event.chat_id }}</dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.userId') }}</dt>
                                    <dd class="monospace">{{ event.initiated_by_user_id }}</dd>
                                </div>
                                <div>
                                    <dt>{{ t('dashboard.fields.sourceMessageId') }}</dt>
                                    <dd class="monospace">{{ event.source_message_id }}</dd>
                                </div>
                            </dl>

                            <div class="json-grid">
                                <div>
                                    <h2>{{ t('dashboard.fields.startDateInput') }}</h2>
                                    <pre>{{ formatJson(event.event_date_input) }}</pre>
                                </div>
                                <div v-if="event.event_end_date_input">
                                    <h2>{{ t('dashboard.fields.endDateInput') }}</h2>
                                    <pre>{{ formatJson(event.event_end_date_input) }}</pre>
                                </div>
                            </div>
                        </div>
                    </q-expansion-item>
                </template>
            </q-list>
        </section>
    </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { eventTags, professionCategories } from 'src/utils/model';
import { listRecordedEvents } from 'src/utils/recordedEventsApi';
import type {
    EventContinent,
    EventCoordinates,
    EventLocation,
    EventTag,
    ProfessionCategory,
    RecordedEvent,
} from 'src/utils/model';

interface DashboardFilters {
    keyword: string | null;
    tags: EventTag[];
    affectedProfessionCategories: ProfessionCategory[];
    responseProfessionCategories: ProfessionCategory[];
}

function emptyFilters(): DashboardFilters {
    return {
        keyword: '',
        tags: [],
        affectedProfessionCategories: [],
        responseProfessionCategories: [],
    };
}

const { locale, t } = useI18n();
const appliedFilters = ref<DashboardFilters>(emptyFilters());
const draftFilters = ref<DashboardFilters>(emptyFilters());
const events = ref<RecordedEvent[]>([]);
const error = ref('');
const loading = ref(true);

const tagOptions = computed(() =>
    eventTags.map((tag) => ({
        label: eventTagLabel(tag),
        value: tag,
    })),
);

const professionOptions = computed(() =>
    professionCategories.map((category) => ({
        label: professionLabel(category),
        value: category,
    })),
);

const hasAppliedFilters = computed(
    () =>
        Boolean(appliedFilters.value.keyword?.trim()) ||
        appliedFilters.value.tags.length > 0 ||
        appliedFilters.value.affectedProfessionCategories.length > 0 ||
        appliedFilters.value.responseProfessionCategories.length > 0,
);

async function loadEvents() {
    loading.value = true;
    error.value = '';

    try {
        events.value = await listRecordedEvents(appliedFilters.value);
    } catch (err) {
        error.value = err instanceof Error ? err.message : t('errors.loadRecordedEvents');
    } finally {
        loading.value = false;
    }
}

async function applyFilters() {
    appliedFilters.value = {
        keyword: draftFilters.value.keyword?.trim() || '',
        tags: [...draftFilters.value.tags],
        affectedProfessionCategories: [...draftFilters.value.affectedProfessionCategories],
        responseProfessionCategories: [...draftFilters.value.responseProfessionCategories],
    };
    await loadEvents();
}

async function clearFilters() {
    draftFilters.value = emptyFilters();
    appliedFilters.value = emptyFilters();
    await loadEvents();
}

function eventTagLabel(tag: EventTag) {
    return t(`dashboard.tags.${tag}`);
}

function professionLabel(category: ProfessionCategory) {
    return t(`profile.categories.${category}`);
}

function formatSeverity(value: number | null) {
    if (value === null) {
        return t('dashboard.severity.notRated');
    }
    return `${new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }).format(value)}/10`;
}

function formatDate(value: string) {
    return new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}

function formatEventDateRange(event: RecordedEvent) {
    const start = event.event_datetime
        ? formatDate(event.event_datetime)
        : formatDate(event.created_at);
    if (!event.event_end_datetime) {
        return start;
    }
    return `${start} – ${formatDate(event.event_end_datetime)}`;
}

function formatLocation(location: EventLocation) {
    if (location.raw_text) {
        return location.raw_text;
    }
    return (
        [
            location.address,
            location.place_name,
            location.city,
            location.region,
            location.country_code,
            location.continent ? continentLabel(location.continent) : null,
        ]
            .filter(Boolean)
            .join(', ') || '-'
    );
}

function formatCoordinates(coordinates: EventCoordinates) {
    return `${coordinates.latitude.toFixed(5)}, ${coordinates.longitude.toFixed(5)}`;
}

function continentLabel(continent: EventContinent) {
    return t(`dashboard.continents.${continent}`);
}

function formatJson(value: unknown) {
    return JSON.stringify(value, null, 2);
}

onMounted(() => {
    void loadEvents();
});
</script>

<style scoped lang="scss">
.dashboard-page {
    padding: 32px;
}

.dashboard-content {
    max-width: 1080px;
}

.header-row {
    align-items: center;
    display: flex;
    gap: 24px;
    justify-content: space-between;
    margin-bottom: 24px;
}

h1 {
    font-size: 32px;
    line-height: 1.2;
    margin: 0 0 6px;
}

p {
    color: #667085;
    margin: 0;
}

.filters-card {
    margin-bottom: 20px;
}

.filters-title {
    font-size: 18px;
    margin: 0 0 16px;
}

.filters-form {
    display: grid;
    gap: 16px;
}

.filters-grid {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

.filter-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
}

.event-list {
    background: white;
}

.event-title {
    font-weight: 600;
}

.event-meta {
    color: #667085;
    font-size: 13px;
    min-width: 180px;
    text-align: right;
}

.event-details {
    background: #f7f8fa;
    padding: 18px 24px 24px;
}

dl {
    display: grid;
    gap: 14px 24px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 0 0 20px;
}

dt {
    color: #667085;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
    margin-bottom: 4px;
    text-transform: uppercase;
}

dd {
    margin: 0;
    overflow-wrap: anywhere;
}

.monospace,
pre {
    font-family: 'Roboto Mono', monospace;
}

.json-grid {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

h2 {
    font-size: 14px;
    margin: 0 0 8px;
}

pre {
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.45;
    margin: 0;
    max-height: 260px;
    overflow: auto;
    padding: 12px;
    user-select: text;
}

@media (max-width: 760px) {
    .dashboard-page {
        padding: 20px;
    }

    .header-row {
        align-items: stretch;
        flex-direction: column;
    }

    .event-meta {
        display: none;
    }

    dl,
    .json-grid,
    .filters-grid {
        grid-template-columns: 1fr;
    }

    .filter-actions {
        justify-content: stretch;
    }

    .filter-actions :deep(.q-btn) {
        flex: 1;
    }
}
</style>
