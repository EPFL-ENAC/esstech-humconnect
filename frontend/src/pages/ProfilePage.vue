<template>
    <q-page class="profile-page">
        <section class="profile-content">
            <div class="header-row">
                <div>
                    <h1>{{ t('profile.title') }}</h1>
                    <p>{{ t('profile.subtitle') }}</p>
                </div>
            </div>

            <q-banner v-if="error" class="bg-red-1 text-red-9 q-mb-md" rounded>
                {{ error }}
            </q-banner>

            <q-card flat bordered class="identity-card q-mb-md">
                <q-card-section>
                    <h2>{{ t('profile.identity') }}</h2>
                    <dl>
                        <div>
                            <dt>{{ t('profile.fields.name') }}</dt>
                            <dd>{{ displayName }}</dd>
                        </div>
                        <div>
                            <dt>{{ t('profile.fields.email') }}</dt>
                            <dd>{{ profile?.email || '-' }}</dd>
                        </div>
                        <div>
                            <dt>{{ t('profile.fields.username') }}</dt>
                            <dd>{{ profile?.username || '-' }}</dd>
                        </div>
                    </dl>
                </q-card-section>
            </q-card>

            <q-card flat bordered>
                <q-card-section>
                    <h2>{{ t('profile.details') }}</h2>

                    <q-form class="profile-form" @submit.prevent="saveProfile">
                        <q-input
                            v-model="form.profession"
                            outlined
                            :disable="loading || saving"
                            :label="t('profile.fields.profession')"
                            :placeholder="t('profile.placeholders.profession')"
                        />

                        <q-select
                            v-model="form.profession_category"
                            outlined
                            emit-value
                            map-options
                            clearable
                            :disable="loading || saving"
                            :label="t('profile.fields.professionCategory')"
                            :options="categoryOptions"
                        />

                        <q-input
                            v-model="form.center_address"
                            outlined
                            :disable="loading || saving"
                            :label="t('profile.fields.centerAddress')"
                            :placeholder="t('profile.placeholders.centerAddress')"
                        />

                        <q-input
                            v-model.number="form.action_radius_km"
                            outlined
                            type="number"
                            min="0"
                            suffix="km"
                            :disable="loading || saving"
                            :label="t('profile.fields.actionRadius')"
                            :rules="radiusRules"
                        />

                        <q-input
                            v-model="form.location_extra"
                            outlined
                            type="textarea"
                            autogrow
                            class="full-width"
                            :disable="loading || saving"
                            :label="t('profile.fields.locationExtra')"
                            :placeholder="t('profile.placeholders.locationExtra')"
                        />

                        <q-input
                            v-model="form.organisation"
                            outlined
                            :disable="loading || saving"
                            :label="t('profile.fields.organisation')"
                            :placeholder="t('profile.placeholders.organisation')"
                        />

                        <q-select
                            v-model="form.mother_tongue"
                            outlined
                            emit-value
                            map-options
                            clearable
                            :disable="loading || saving"
                            :label="t('profile.fields.motherTongue')"
                            :options="languageOptions"
                        />

                        <div class="actions full-width">
                            <q-btn
                                flat
                                color="primary"
                                :disable="loading || saving"
                                :label="t('profile.reset')"
                                @click="resetForm"
                            />
                            <q-btn
                                color="primary"
                                icon="save"
                                type="submit"
                                :disable="loading"
                                :loading="saving"
                                :label="t('profile.save')"
                            />
                        </div>
                    </q-form>
                </q-card-section>

                <q-inner-loading :showing="loading">
                    <q-spinner color="primary" size="32px" />
                    <div class="q-mt-sm">{{ t('profile.loading') }}</div>
                </q-inner-loading>
            </q-card>
        </section>
    </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';
import { languageCodes, languageLabel } from 'src/utils/languages';
import { getProfile, updateProfile } from 'src/utils/profileApi';
import type { ProfessionCategory, UserProfile, UserProfileEditableFields } from 'src/utils/model';

const professionCategories: ProfessionCategory[] = [
    'medical_clinical',
    'community_health',
    'wash',
    'logistics_supply',
    'surveillance_epidemiology',
    'coordination_cluster',
    'safe_burial_community_response',
    'biomedical_equipment',
    'infrastructure_energy',
    'hq_programme_referent',
    'local_ngo_partner',
    'other',
];

const emptyForm: UserProfileEditableFields = {
    profession: null,
    profession_category: null,
    center_address: null,
    action_radius_km: null,
    location_extra: null,
    organisation: null,
    mother_tongue: null,
};

const $q = useQuasar();
const { locale, t } = useI18n();
const error = ref('');
const form = ref<UserProfileEditableFields>({ ...emptyForm });
const loading = ref(true);
const profile = ref<UserProfile | null>(null);
const saving = ref(false);

const categoryOptions = computed(() =>
    professionCategories.map((category) => ({
        label: t(`profile.categories.${category}`),
        value: category,
    })),
);

const languageOptions = computed(() =>
    languageCodes
        .map((code) => ({
            label: languageLabel(code, locale.value),
            value: code,
        }))
        .sort((left, right) => left.label.localeCompare(right.label, locale.value)),
);

const displayName = computed(() => {
    const parts = [profile.value?.first_name, profile.value?.last_name].filter(Boolean);
    return parts.length > 0 ? parts.join(' ') : '-';
});

const radiusRules = computed(() => [
    (value: number | string | null) =>
        value === null ||
        value === '' ||
        Number(value) >= 0 ||
        t('profile.validation.positiveRadius'),
]);

function editableFieldsFromProfile(value: UserProfile): UserProfileEditableFields {
    return {
        profession: value.profession,
        profession_category: value.profession_category,
        center_address: value.center_address,
        action_radius_km: value.action_radius_km,
        location_extra: value.location_extra,
        organisation: value.organisation,
        mother_tongue: value.mother_tongue,
    };
}

function normalizeText(value: string | null): string | null {
    const trimmed = value?.trim() || '';
    return trimmed || null;
}

function normalizeRadius(): number | null {
    const radius = form.value.action_radius_km as number | string | null;
    if (radius === null || radius === '') {
        return null;
    }
    return Number(radius);
}

function normalizeForm(): UserProfileEditableFields {
    return {
        profession: normalizeText(form.value.profession),
        profession_category: form.value.profession_category,
        center_address: normalizeText(form.value.center_address),
        action_radius_km: normalizeRadius(),
        location_extra: normalizeText(form.value.location_extra),
        organisation: normalizeText(form.value.organisation),
        mother_tongue: form.value.mother_tongue,
    };
}

async function loadProfile() {
    loading.value = true;
    error.value = '';

    try {
        profile.value = await getProfile();
        form.value = editableFieldsFromProfile(profile.value);
    } catch (err) {
        error.value = err instanceof Error ? err.message : t('errors.loadProfile');
    } finally {
        loading.value = false;
    }
}

function resetForm() {
    if (profile.value) {
        form.value = editableFieldsFromProfile(profile.value);
    } else {
        form.value = { ...emptyForm };
    }
}

async function saveProfile() {
    saving.value = true;
    error.value = '';

    try {
        profile.value = await updateProfile(normalizeForm());
        form.value = editableFieldsFromProfile(profile.value);
        $q.notify({
            color: 'positive',
            icon: 'check',
            message: t('profile.saved'),
        });
    } catch (err) {
        error.value = err instanceof Error ? err.message : t('errors.saveProfile');
    } finally {
        saving.value = false;
    }
}

onMounted(() => {
    void loadProfile();
});
</script>

<style scoped lang="scss">
.profile-page {
    padding: 32px;
}

.profile-content {
    max-width: 860px;
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

h2 {
    font-size: 18px;
    line-height: 1.3;
    margin: 0 0 18px;
}

p {
    color: #667085;
    margin: 0;
}

dl {
    display: grid;
    gap: 14px 24px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin: 0;
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

.profile-form {
    display: grid;
    gap: 18px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
}

.full-width {
    grid-column: 1 / -1;
}

.actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
}

@media (max-width: 760px) {
    .profile-page {
        padding: 20px;
    }

    dl,
    .profile-form {
        grid-template-columns: 1fr;
    }

    .actions {
        align-items: stretch;
        flex-direction: column-reverse;
    }
}
</style>
