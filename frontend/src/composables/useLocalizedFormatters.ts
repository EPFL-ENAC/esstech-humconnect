import { useI18n } from 'vue-i18n';

const defaultDateOptions: Intl.DateTimeFormatOptions = {
    dateStyle: 'medium',
    timeStyle: 'short',
};

interface LocalizedFormatters {
    formatDate: (
        value: string | null | undefined,
        emptyValue: string,
        options?: Intl.DateTimeFormatOptions,
    ) => string;
    formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string;
}

export function useLocalizedFormatters(): LocalizedFormatters {
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

    return { formatDate, formatNumber };
}
