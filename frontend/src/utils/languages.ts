import type { LanguageCode } from 'src/utils/model';

export const languageCodes: LanguageCode[] = [
    'ar',
    'bn',
    'de',
    'en',
    'es',
    'fa',
    'fr',
    'hi',
    'id',
    'it',
    'ja',
    'km',
    'ko',
    'lo',
    'ms',
    'my',
    'ne',
    'pa',
    'prs',
    'ps',
    'pt',
    'ru',
    'si',
    'sw',
    'ta',
    'te',
    'th',
    'tl',
    'tr',
    'uk',
    'ur',
    'vi',
    'yue',
    'zh',
];

export function languageLabel(code: LanguageCode, locale: string): string {
    const displayName = new Intl.DisplayNames([locale], { type: 'language' }).of(code);
    return displayName && displayName !== code ? displayName : code.toUpperCase();
}
