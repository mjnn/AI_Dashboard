import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import zh from "./locales/zh.json";
import { LOCALE_STORAGE_KEY, normalizeLocale, type AppLocale } from "./types";

const saved =
  typeof localStorage !== "undefined"
    ? localStorage.getItem(LOCALE_STORAGE_KEY)
    : null;

const initial = normalizeLocale(saved ?? undefined);

void i18n.use(initReactI18next).init({
  resources: {
    zh: { translation: zh },
    en: { translation: en },
  },
  lng: initial,
  fallbackLng: "zh",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (lng) => {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(LOCALE_STORAGE_KEY, lng);
  }
  document.documentElement.lang = lng;
});

document.documentElement.lang = initial;

export function getApiLocale(): AppLocale {
  return normalizeLocale(i18n.language);
}

export default i18n;
