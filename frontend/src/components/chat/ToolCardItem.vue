<template>
    <component
        :is="href ? 'a' : 'article'"
        class="context-card"
        :class="{ 'context-card-link': href }"
        :href="href ?? undefined"
        :target="href ? '_blank' : undefined"
        :rel="href ? 'noopener noreferrer' : undefined"
        :style="{ '--color': color }"
    >
        <header class="card-header">
            <div class="card-heading">
                <span class="eyebrow">{{ eyebrow }}</span>
                <q-icon v-if="href" name="open_in_new" size="15px" />
            </div>
            <h5>{{ title }}</h5>
        </header>

        <div class="card-content">
            <slot name="content" />
        </div>

        <dl v-if="extraInfo?.length" class="card-meta">
            <div v-for="(info, index) in extraInfo" :key="index">
                <dt><q-icon :name="info.icon" /></dt>
                <dd>{{ info.value }}</dd>
            </div>
        </dl>
    </component>
</template>

<script setup lang="ts">
interface ExtraInfo {
    icon: string;
    value: string;
}

defineProps<{
    href?: string | undefined;
    color?: string | undefined;
    eyebrow: string;
    title: string;
    extraInfo?: ExtraInfo[] | undefined;
}>();
</script>

<style scoped lang="scss">
.context-card {
    background: white;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    color: #344054;
    display: grid;
    grid-row: span 3;
    grid-template-rows: subgrid;
    min-height: 178px;
    padding: 11px;
    text-decoration: none;
}

.context-card-link {
    cursor: pointer;
    transition:
        border-color 140ms ease,
        box-shadow 140ms ease,
        transform 140ms ease;
}

.context-card-link:hover,
.context-card-link:focus-visible {
    border-color: var(--color, #84adff);
    box-shadow: 0 4px 12px rgb(21 112 239 / 12%);
    outline: none;
    transform: translateY(-1px);
}

.card-header,
.card-content {
    border-bottom: 1px solid #eaecf0;
    padding-bottom: 0.5rem;
}

.card-heading {
    align-items: center;
    color: var(--color, #344054);
    display: flex;
    justify-content: space-between;
}

.eyebrow {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.context-card h5 {
    color: #101828;
    display: -webkit-box;
    font-size: 13px;
    font-weight: 650;
    line-height: 1.35;
    margin: 8px 0 6px;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.card-meta {
    color: #667085;
    font-size: 11px;
    margin: auto 0 0;
}

.card-meta > div {
    align-items: flex-start;
    display: flex;
    gap: 5px;
    margin-top: 5px;
}

.card-meta dt,
.card-meta dd {
    margin: 0;
}

.card-meta dt {
    color: #98a2b3;
    flex: 0 0 auto;
    line-height: 1;
}

.card-meta dd {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
}
</style>
