export function truncateUnicode(value: string, maxLength: number): string {
    if (value.length <= maxLength) {
        return value;
    }

    return `${value.slice(0, maxLength - 1)}…`;
}

export function prettyPrintJson(value: unknown): string {
    return JSON.stringify(value, null, 2) ?? '';
}
