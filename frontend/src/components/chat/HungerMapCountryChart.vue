<template>
    <section class="country-chart" :aria-label="chartAriaLabel">
        <header class="chart-heading">
            <div>
                <h4>{{ estimate.name }}</h4>
            </div>
        </header>

        <VChart class="chart" :option="chartOption" autoresize />

        <p class="analysis-scope-note">
            <q-icon name="info_outline" size="16px" />
            <span>{{ t('chat.activities.hungerMap.analysisScopeNote') }}</span>
        </p>

        <dl class="chart-details">
            <div>
                <dt>{{ t('chat.activities.hungerMap.referencePeriod') }}</dt>
                <dd>{{ estimate.reference_period }}</dd>
            </div>
            <div>
                <dt>{{ t('chat.activities.hungerMap.analysisDate') }}</dt>
                <dd>{{ formattedAnalysisDate }}</dd>
            </div>
            <div>
                <dt>{{ t('chat.activities.hungerMap.dataSource') }}</dt>
                <dd>{{ estimate.data_source }}</dd>
            </div>
        </dl>

        <a class="source-link" :href="sourceUrl" target="_blank" rel="noopener noreferrer">
            {{ t('chat.activities.hungerMap.openSource') }}
            <q-icon name="open_in_new" size="14px" />
        </a>
    </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { EChartsOption, TooltipComponentFormatterCallbackParams } from 'echarts';
import { BarChart } from 'echarts/charts';
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import type { HungerMapCountryEstimate, HungerMapPhaseEstimate } from './toolCallSchemas';

use([AriaComponent, BarChart, CanvasRenderer, GridComponent, TooltipComponent]);

interface IpcPhaseLevel {
    code: 'phase_3' | 'phase_4' | 'phase_5';
    color: string;
    estimate: HungerMapPhaseEstimate;
    label: string;
}

const props = defineProps<{
    estimate: HungerMapCountryEstimate;
    sourceUrl: string;
}>();

const { t } = useI18n();
const { formatDate, formatNumber } = useLocalizedFormatters();
const phaseLevels = computed<IpcPhaseLevel[]>(() => [
    {
        code: 'phase_3',
        color: '#f2c94c',
        estimate: subtractPhaseEstimate(
            props.estimate.phase_3_or_above,
            props.estimate.phase_4_or_above,
        ),
        label: t('chat.activities.hungerMap.ipcPhases.phaseThree'),
    },
    {
        code: 'phase_4',
        color: '#e8752d',
        estimate: subtractPhaseEstimate(props.estimate.phase_4_or_above, props.estimate.phase_5),
        label: t('chat.activities.hungerMap.ipcPhases.phaseFour'),
    },
    {
        code: 'phase_5',
        color: '#8b0000',
        estimate: props.estimate.phase_5,
        label: t('chat.activities.hungerMap.ipcPhases.phaseFive'),
    },
]);
const populationAxisMaximum = computed(() => {
    const cumulativeEstimates = [
        props.estimate.phase_3_or_above,
        props.estimate.phase_4_or_above,
        props.estimate.phase_5,
    ];
    const populationBasis = cumulativeEstimates.find(
        (estimate) => estimate.percentage > 0 && estimate.population > 0,
    );
    if (populationBasis) {
        return Math.max(
            1,
            Math.ceil((populationBasis.population * 100) / populationBasis.percentage),
        );
    }

    return Math.max(1, ...phaseLevels.value.map((level) => level.estimate.population));
});
const chartAriaLabel = computed(() =>
    t('chat.activities.hungerMap.countryChartAriaLabel', {
        country: props.estimate.name,
    }),
);
const formattedAnalysisDate = computed(() =>
    formatDate(props.estimate.analysis_date, props.estimate.analysis_date, {
        dateStyle: 'medium',
        timeZone: 'UTC',
    }),
);
const chartOption = computed<EChartsOption>(() => ({
    animationDuration: 350,
    aria: {
        enabled: true,
        description: chartAriaLabel.value,
    },
    grid: {
        bottom: 8,
        containLabel: true,
        left: 28,
        right: 34,
        top: 8,
    },
    tooltip: {
        axisPointer: {
            type: 'shadow',
        },
        formatter: (params: TooltipComponentFormatterCallbackParams) => {
            const dataPoint = Array.isArray(params) ? params[0] : params;
            const level = dataPoint ? phaseLevels.value[dataPoint.dataIndex] : undefined;
            if (!level) {
                return '';
            }

            return [
                level.label,
                `${t('chat.activities.hungerMap.percentageAxis')}: ${t(
                    'chat.activities.hungerMap.percentageValue',
                    {
                        value: formatNumber(level.estimate.percentage, {
                            maximumFractionDigits: 5,
                        }),
                    },
                )}`,
                `${t('chat.activities.hungerMap.populationAxis')}: ${formatNumber(
                    level.estimate.population,
                )}`,
            ].join('\n');
        },
        renderMode: 'richText',
        trigger: 'axis',
    },
    xAxis: {
        axisLabel: {
            color: '#475467',
            fontSize: 11,
            interval: 0,
        },
        axisTick: {
            alignWithLabel: true,
        },
        data: phaseLevels.value.map((level) => level.label),
        type: 'category',
    },
    yAxis: [
        {
            axisLabel: {
                color: '#667085',
                formatter: (value: string | number) =>
                    t('chat.activities.hungerMap.percentageValue', {
                        value: formatNumber(Number(value), { maximumFractionDigits: 0 }),
                    }),
            },
            max: 100,
            min: 0,
            name: t('chat.activities.hungerMap.percentageAxis'),
            nameGap: 52,
            nameLocation: 'middle',
            nameTextStyle: {
                color: '#667085',
                fontSize: 11,
            },
            splitLine: {
                lineStyle: {
                    color: '#eaecf0',
                },
            },
            interval: 20,
            splitNumber: 5,
            type: 'value',
        },
        {
            axisLabel: {
                color: '#667085',
                formatter: (value: string | number) =>
                    formatNumber(Number(value), {
                        maximumFractionDigits: 1,
                        notation: 'compact',
                    }),
            },
            max: populationAxisMaximum.value,
            min: 0,
            name: t('chat.activities.hungerMap.populationAxis'),
            nameGap: 52,
            nameLocation: 'middle',
            nameTextStyle: {
                color: '#667085',
                fontSize: 11,
            },
            position: 'right',
            splitLine: {
                show: false,
            },
            interval: populationAxisMaximum.value / 5,
            splitNumber: 5,
            type: 'value',
        },
    ],
    series: [
        {
            barMaxWidth: 64,
            data: phaseLevels.value.map((level) => ({
                itemStyle: {
                    color: level.color,
                },
                value: level.estimate.percentage,
            })),
            emphasis: {
                focus: 'series',
            },
            name: t('chat.activities.hungerMap.ipcBreakdown'),
            type: 'bar',
            yAxisIndex: 0,
        },
    ],
}));

function subtractPhaseEstimate(
    inclusiveEstimate: HungerMapPhaseEstimate,
    higherPhaseEstimate: HungerMapPhaseEstimate,
): HungerMapPhaseEstimate {
    return {
        percentage: Math.max(
            0,
            Math.round((inclusiveEstimate.percentage - higherPhaseEstimate.percentage) * 100_000) /
                100_000,
        ),
        population: Math.max(0, inclusiveEstimate.population - higherPhaseEstimate.population),
    };
}
</script>

<style scoped lang="scss">
.country-chart {
    display: grid;
    gap: 10px;
    min-width: 0;
}

.chart-heading {
    align-items: flex-start;
    display: flex;
    gap: 16px;
    justify-content: space-between;
}

.chart-heading h4 {
    color: #344054;
    font-size: 14px;
    margin: 0 0 2px;
}

.chart-heading p {
    color: #667085;
    font-size: 11px;
    margin: 0;
}

.class-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 5px 10px;
    justify-content: flex-end;
}

.legend-item {
    align-items: center;
    color: #475467;
    display: inline-flex;
    font-size: 10px;
    gap: 4px;
    white-space: nowrap;
}

.legend-swatch {
    border: 1px solid rgba(0, 0, 0, 0.14);
    border-radius: 2px;
    height: 10px;
    width: 16px;
}

.chart {
    height: 340px;
    min-width: 0;
    width: 100%;
}

.analysis-scope-note {
    align-items: flex-start;
    background: #f8fafc;
    border-radius: 4px;
    color: #475467;
    display: flex;
    font-size: 11px;
    gap: 6px;
    margin: 0;
    padding: 8px 10px;
}

.analysis-scope-note .q-icon {
    color: #007dbc;
    flex: 0 0 auto;
}

.chart-details {
    display: grid;
    gap: 6px 12px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin: 0;
}

.chart-details div {
    min-width: 0;
}

.chart-details dt {
    color: #667085;
    font-size: 10px;
}

.chart-details dd {
    color: #344054;
    font-size: 11px;
    margin: 1px 0 0;
    overflow-wrap: anywhere;
}

.source-link {
    align-items: center;
    color: #007dbc;
    display: inline-flex;
    font-size: 11px;
    gap: 3px;
    justify-self: start;
    text-decoration: none;
}

.source-link:hover {
    text-decoration: underline;
}

@media (max-width: 700px) {
    .chart-heading {
        display: grid;
    }

    .class-legend {
        justify-content: flex-start;
    }

    .chart {
        height: 300px;
    }

    .chart-details {
        grid-template-columns: 1fr;
    }
}
</style>
