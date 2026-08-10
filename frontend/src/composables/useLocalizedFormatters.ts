import { useI18n } from 'vue-i18n';

const defaultDateOptions: Intl.DateTimeFormatOptions = {
    dateStyle: 'medium',
    timeStyle: 'short',
};

interface Coordinates {
    latitude: number;
    longitude: number;
}

export function useLocalizedFormatters() {
    const { locale } = useI18n();

    function formatDate(
        value: string | null | undefined,
        emptyValue: string,
        options: Intl.DateTimeFormatOptions = defaultDateOptions,
    ): string {
        if (!value) {
            return emptyValue;
        }

        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }

        return new Intl.DateTimeFormat(locale.value, options).format(date);
    }

    function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
        return new Intl.NumberFormat(locale.value, options).format(value);
    }

    function formatCoordinates(
        coordinates: Coordinates,
        options?: Intl.NumberFormatOptions,
    ): string {
        return `${formatNumber(coordinates.latitude, options)}, ${formatNumber(coordinates.longitude, options)}`;
    }

    function formatDateRange(
        start: string | null | undefined,
        end: string | null | undefined,
        emptyValue: string,
        options: Intl.DateTimeFormatOptions = defaultDateOptions,
    ): string {
        const formattedStart = formatDate(start, emptyValue, options);
        if (!end) {
            return formattedStart;
        }

        return `${formattedStart} – ${formatDate(end, emptyValue, options)}`;
    }

    return { formatCoordinates, formatDate, formatDateRange, formatNumber };
}
