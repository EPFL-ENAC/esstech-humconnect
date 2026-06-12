/**
 * Returns the i18n `t` function for use outside Vue components (e.g. Pinia stores).
 * The i18n instance is attached to `window.i18nGlobal` by the boot/i18n.ts boot file.
 */
export function getI18nT(): (key: string, params?: Record<string, unknown>) => string {
  if (typeof window !== 'undefined') {
    const win = window as unknown as {
      i18nGlobal?: { t: (key: string, params?: Record<string, unknown>) => string };
    };
    if (win.i18nGlobal) {
      return win.i18nGlobal.t;
    }
  }
  return (key: string) => key;
}
