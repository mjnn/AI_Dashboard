export const SUPPORTED_LOCALES = ["zh", "en", "de"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export const LOCALE_STORAGE_KEY = "ai-dashboard-locale";

export function isAppLocale(value: string): value is AppLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function normalizeLocale(value: string | undefined): AppLocale {
  if (value && isAppLocale(value)) {
    return value;
  }
  const short = value?.split("-")[0];
  if (short && isAppLocale(short)) {
    return short;
  }
  return "zh";
}
