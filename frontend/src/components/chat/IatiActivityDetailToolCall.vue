<template>
    <ChatActivityBlock
        :title="payload.tool_label"
        :summary="summary"
        icon="account_balance"
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
                    <article v-if="result" class="activity-detail">
                        <header class="activity-header">
                            <div class="activity-heading">
                                <span class="provider-label">
                                    {{ t('chat.activities.iati.provider') }}
                                </span>
                                <q-badge v-if="result.status" outline color="deep-purple-7">
                                    {{ result.status }}
                                </q-badge>
                            </div>
                            <h5>{{ result.title }}</h5>
                            <div class="activity-id">{{ result.activity_id }}</div>
                        </header>

                        <p v-if="result.description" class="activity-description">
                            {{ result.description }}
                        </p>
                        <p v-else class="activity-description activity-description-empty">
                            {{ t('chat.activities.iati.noDescription') }}
                        </p>

                        <div
                            v-if="result.commitment_usd !== null || result.spend_usd !== null"
                            class="finance-grid"
                        >
                            <div v-if="result.commitment_usd !== null" class="finance-stat">
                                <span>{{ t('chat.activities.iati.commitment') }}</span>
                                <strong>{{ formatUsd(result.commitment_usd) }}</strong>
                            </div>
                            <div v-if="result.spend_usd !== null" class="finance-stat">
                                <span>{{ t('chat.activities.iati.spend') }}</span>
                                <strong>{{ formatUsd(result.spend_usd) }}</strong>
                            </div>
                        </div>

                        <dl class="activity-meta">
                            <div>
                                <dt><q-icon name="corporate_fare" /></dt>
                                <dd>
                                    <span>{{
                                        t('chat.activities.iati.reportingOrganisation')
                                    }}</span>
                                    {{ reportingOrganisation }}
                                </dd>
                            </div>
                            <div>
                                <dt><q-icon name="date_range" /></dt>
                                <dd>
                                    <span>{{ t('chat.activities.iati.activityPeriod') }}</span>
                                    {{ activityPeriod }}
                                </dd>
                            </div>
                        </dl>

                        <div v-if="hasReferences" class="reference-grid">
                            <section v-if="result.recipient_countries.length">
                                <h6>
                                    <q-icon name="public" />
                                    {{ t('chat.activities.iati.recipientCountries') }}
                                </h6>
                                <div class="reference-chips">
                                    <q-chip
                                        v-for="(country, index) in result.recipient_countries"
                                        :key="`${country.code}-${index}`"
                                        dense
                                        square
                                        outline
                                        color="deep-purple-7"
                                    >
                                        {{ countryLabel(country) }}
                                    </q-chip>
                                </div>
                            </section>

                            <section v-if="result.sectors.length">
                                <h6>
                                    <q-icon name="category" />
                                    {{ t('chat.activities.iati.sectors') }}
                                </h6>
                                <div class="reference-chips">
                                    <q-chip
                                        v-for="(sector, index) in result.sectors"
                                        :key="`${sector.code}-${index}`"
                                        dense
                                        square
                                        outline
                                        color="deep-purple-7"
                                    >
                                        {{ sectorLabel(sector) }}
                                    </q-chip>
                                </div>
                            </section>

                            <section v-if="result.participating_organisations.length">
                                <h6>
                                    <q-icon name="groups" />
                                    {{ t('chat.activities.iati.participatingOrganisations') }}
                                </h6>
                                <div class="participant-list">
                                    <div
                                        v-for="(
                                            organisation, index
                                        ) in result.participating_organisations"
                                        :key="`${organisation.reference}-${index}`"
                                    >
                                        <strong>{{
                                            participatingOrganisationName(organisation)
                                        }}</strong>
                                        <span v-if="organisation.role">{{
                                            organisation.role
                                        }}</span>
                                    </div>
                                </div>
                            </section>

                            <section v-if="result.documents.length">
                                <h6>
                                    <q-icon name="description" />
                                    {{ t('chat.activities.iati.documents') }}
                                </h6>
                                <div class="document-list">
                                    <a
                                        v-for="(document, index) in result.documents"
                                        :key="`${document.url}-${index}`"
                                        :href="document.url"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <q-icon name="open_in_new" />
                                        <span>{{ documentTitle(document, index) }}</span>
                                    </a>
                                </div>
                            </section>
                        </div>

                        <a
                            class="source-link"
                            :href="result.source_url"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            {{ t('chat.activities.iati.openActivity') }}
                            <q-icon name="arrow_forward" />
                        </a>
                    </article>
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
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import ChatActivityBlock from './ChatActivityBlock.vue';
import ToolCallRawContent from './ToolCallRawContent.vue';
import ToolCallVisualizationSkeleton from './ToolCallVisualizationSkeleton.vue';
import type { IatiActivityDetail, IatiActivityDetailToolCallPayload } from './toolCallSchemas';

const props = defineProps<{
    payload: IatiActivityDetailToolCallPayload;
}>();

const toolColor = '#6941c6';
const { t } = useI18n();
const { formatDateRange, formatNumber } = useLocalizedFormatters();
const result = computed(() => (props.payload.status === 'finished' ? props.payload.answer : null));
const mode = computed<'visual-and-raw' | 'raw-only'>(() =>
    props.payload.status === 'running' || result.value ? 'visual-and-raw' : 'raw-only',
);
const visualizationQuery = computed(() => ({
    label: t('chat.activities.iati.activityId'),
    value: props.payload.arguments.activity_id,
    icon: 'fingerprint',
}));
const summary = computed(() => {
    if (props.payload.status === 'running') {
        return t('chat.activities.iati.loadingActivity');
    }
    if (result.value) {
        return t('chat.activities.iati.activityReady');
    }
    return t(`chat.activities.status.${props.payload.status}`);
});
const reportingOrganisation = computed(() => {
    const organisation = result.value?.reporting_organisation;
    return organisation?.name ?? organisation?.reference ?? t('chat.activities.iati.notAvailable');
});
const activityPeriod = computed(() =>
    formatDateRange(
        result.value?.start_date,
        result.value?.end_date,
        t('chat.activities.iati.unknownDate'),
        { dateStyle: 'medium' },
    ),
);
const hasReferences = computed(
    () =>
        Boolean(result.value?.recipient_countries.length) ||
        Boolean(result.value?.sectors.length) ||
        Boolean(result.value?.participating_organisations.length) ||
        Boolean(result.value?.documents.length),
);

type RecipientCountry = IatiActivityDetail['recipient_countries'][number];
type Sector = IatiActivityDetail['sectors'][number];
type ParticipatingOrganisation = IatiActivityDetail['participating_organisations'][number];
type Document = IatiActivityDetail['documents'][number];

function formatUsd(value: number): string {
    return formatNumber(value, {
        style: 'currency',
        currency: 'USD',
        notation: 'compact',
        maximumFractionDigits: 1,
    });
}

function formatPercentage(value: number): string {
    return formatNumber(value, { maximumFractionDigits: 1 }) + '%';
}

function countryLabel(country: RecipientCountry): string {
    return country.percentage === null
        ? country.name
        : `${country.name} · ${formatPercentage(country.percentage)}`;
}

function sectorLabel(sector: Sector): string {
    return sector.percentage === null
        ? sector.code
        : `${sector.code} · ${formatPercentage(sector.percentage)}`;
}

function participatingOrganisationName(organisation: ParticipatingOrganisation): string {
    return (
        organisation.name ?? organisation.reference ?? t('chat.activities.iati.unnamedOrganisation')
    );
}

function documentTitle(document: Document, index: number): string {
    return (
        document.title ??
        t('chat.activities.iati.untitledDocument', {
            number: index + 1,
        })
    );
}
</script>

<style scoped lang="scss">
.activity-detail {
    background: white;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    color: #344054;
    padding: 14px;
}

.activity-header {
    border-bottom: 1px solid #eaecf0;
    padding-bottom: 12px;
}

.activity-heading {
    align-items: center;
    display: flex;
    gap: 8px;
    justify-content: space-between;
}

.provider-label {
    color: #6941c6;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.activity-header h5 {
    color: #101828;
    font-size: 16px;
    font-weight: 650;
    line-height: 1.35;
    margin: 8px 0 4px;
}

.activity-id {
    color: #667085;
    font-family: monospace;
    font-size: 11px;
    overflow-wrap: anywhere;
}

.activity-description {
    color: #475467;
    font-size: 12px;
    line-height: 1.55;
    margin: 12px 0;
    white-space: pre-wrap;
}

.activity-description-empty {
    color: #98a2b3;
    font-style: italic;
}

.finance-grid {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    margin: 12px 0;
}

.finance-stat {
    background: #f9f5ff;
    border: 1px solid #e9d7fe;
    border-radius: 7px;
    display: flex;
    flex-direction: column;
    padding: 9px 10px;
}

.finance-stat span {
    color: #6941c6;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}

.finance-stat strong {
    color: #42307d;
    font-size: 15px;
    margin-top: 2px;
}

.activity-meta {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    margin: 12px 0;
}

.activity-meta > div {
    align-items: flex-start;
    display: flex;
    gap: 7px;
}

.activity-meta dt,
.activity-meta dd {
    margin: 0;
}

.activity-meta dt {
    color: #98a2b3;
}

.activity-meta dd {
    font-size: 12px;
}

.activity-meta dd span {
    color: #667085;
    display: block;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}

.reference-grid {
    border-top: 1px solid #eaecf0;
    display: grid;
    gap: 14px;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    padding-top: 12px;
}

.reference-grid h6 {
    align-items: center;
    color: #475467;
    display: flex;
    font-size: 11px;
    font-weight: 650;
    gap: 5px;
    margin: 0 0 6px;
    text-transform: uppercase;
}

.reference-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.participant-list,
.document-list {
    display: grid;
    gap: 5px;
}

.participant-list > div {
    align-items: baseline;
    display: flex;
    font-size: 11px;
    gap: 6px;
}

.participant-list span {
    color: #667085;
}

.document-list a,
.source-link {
    align-items: center;
    color: #6941c6;
    display: flex;
    font-size: 11px;
    gap: 5px;
    text-decoration: none;
}

.document-list a:hover,
.source-link:hover {
    text-decoration: underline;
}

.source-link {
    border-top: 1px solid #eaecf0;
    font-weight: 650;
    justify-content: flex-end;
    margin-top: 14px;
    padding-top: 10px;
}
</style>
