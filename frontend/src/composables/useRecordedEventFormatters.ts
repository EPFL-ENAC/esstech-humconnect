import { useI18n } from 'vue-i18n';
import { useLocalizedFormatters } from 'src/composables/useLocalizedFormatters';
import type { EventContinent, EventLocation, EventTag } from 'src/utils/model';

export function useRecordedEventFormatters() {
    const { t } = useI18n();
    const { formatNumber } = useLocalizedFormatters();

    function formatContinent(continent: EventContinent | null): string | null {
        return continent ? t(`dashboard.continents.${continent}`) : null;
    }

    function formatLocation(location: EventLocation, emptyValue: string): string {
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
                formatContinent(location.continent),
            ]
                .filter((part): part is string => Boolean(part))
                .join(', ') || emptyValue
        );
    }

    function formatSeverity(
        value: number | null,
        options: Intl.NumberFormatOptions = { maximumFractionDigits: 1 },
    ): string {
        if (value === null) {
            return t('dashboard.severity.notRated');
        }

        return `${formatNumber(value, options)}/10`;
    }

    function formatTag(tag: EventTag): string {
        return t(`dashboard.tags.${tag}`);
    }

    return { formatContinent, formatLocation, formatSeverity, formatTag };
}
