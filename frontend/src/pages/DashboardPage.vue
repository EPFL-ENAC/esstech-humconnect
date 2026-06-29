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

            <q-list bordered separator class="event-list">
                <q-item v-if="loading">
                    <q-item-section>{{ t('dashboard.loading') }}</q-item-section>
                </q-item>

                <q-item v-else-if="events.length === 0">
                    <q-item-section>{{ t('dashboard.empty') }}</q-item-section>
                </q-item>

                <q-expansion-item
                    v-for="event in events"
                    v-else
                    :key="event.id"
                    expand-separator
                    group="recorded-events"
                >
                    <template #header>
                        <q-item-section>
                            <q-item-label class="event-title">{{ event.event_name }}</q-item-label>
                            <q-item-label caption>{{ event.original_text }}</q-item-label>
                        </q-item-section>
                        <q-item-section side class="event-meta">
                            <span>{{ formatDate(event.event_datetime || event.created_at) }}</span>
                        </q-item-section>
                    </template>

                    <div class="event-details">
                        <dl>
                            <div>
                                <dt>{{ t('dashboard.fields.createdAt') }}</dt>
                                <dd>{{ formatDate(event.created_at) }}</dd>
                            </div>
                            <div>
                                <dt>{{ t('dashboard.fields.eventDate') }}</dt>
                                <dd>
                                    {{
                                        event.event_datetime
                                            ? formatDate(event.event_datetime)
                                            : '-'
                                    }}
                                </dd>
                            </div>
                            <div>
                                <dt>{{ t('dashboard.fields.dateQuality') }}</dt>
                                <dd>
                                    {{ event.event_date_granularity }} /
                                    {{ event.event_date_precision }}
                                </dd>
                            </div>
                            <div>
                                <dt>{{ t('dashboard.fields.location') }}</dt>
                                <dd>{{ formatLocation(event.event_location) }}</dd>
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
                                        {{ tag }}
                                    </q-chip>
                                    <span v-if="event.tags.length === 0">-</span>
                                </dd>
                            </div>
                            <div>
                                <dt>{{ t('dashboard.fields.chatId') }}</dt>
                                <dd class="monospace">{{ event.chat_id }}</dd>
                            </div>
                            <div>
                                <dt>{{ t('dashboard.fields.clientId') }}</dt>
                                <dd class="monospace">{{ event.initiated_by_client_id }}</dd>
                            </div>
                            <div>
                                <dt>{{ t('dashboard.fields.sourceMessageId') }}</dt>
                                <dd class="monospace">{{ event.source_message_id }}</dd>
                            </div>
                        </dl>

                        <div class="json-grid">
                            <div>
                                <h2>{{ t('dashboard.fields.dateInput') }}</h2>
                                <pre>{{ formatJson(event.event_date_input) }}</pre>
                            </div>
                            <div>
                                <h2>{{ t('dashboard.fields.locationInput') }}</h2>
                                <pre>{{ formatJson(event.event_location) }}</pre>
                            </div>
                        </div>
                    </div>
                </q-expansion-item>
            </q-list>
        </section>
    </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { listRecordedEvents } from 'src/utils/recordedEventsApi';
import type { RecordedEvent } from 'src/utils/model';

const { locale, t } = useI18n();
const events = ref<RecordedEvent[]>([]);
const error = ref('');
const loading = ref(true);

async function loadEvents() {
    loading.value = true;
    error.value = '';

    try {
        events.value = await listRecordedEvents();
    } catch (err) {
        error.value = err instanceof Error ? err.message : t('errors.loadRecordedEvents');
    } finally {
        loading.value = false;
    }
}

function formatDate(value: string) {
    return new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}

function formatLocation(location: Record<string, unknown>) {
    const value = location.value;
    if (typeof value === 'string' && value.trim()) {
        return value;
    }
    return '-';
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
    .json-grid {
        grid-template-columns: 1fr;
    }
}
</style>
