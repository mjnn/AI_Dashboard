import { useTranslation } from "react-i18next";

import { SUPPORTED_LOCALES, type AppLocale } from "../i18n/types";

const LOCALE_LABEL_KEYS: Record<AppLocale, string> = {
  zh: "lang.zh",
  en: "lang.en",
};

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  return (
    <div
      className="inline-flex rounded-lg border border-slate-200/80 bg-white/80 p-0.5 shadow-sm"
      role="group"
      aria-label={t("lang.label")}
    >
      {SUPPORTED_LOCALES.map((code) => {
        const active = i18n.language === code;
        return (
          <button
            key={code}
            type="button"
            onClick={() => void i18n.changeLanguage(code)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
              active
                ? "bg-slate-800 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
            }`}
            aria-pressed={active}
          >
            {t(LOCALE_LABEL_KEYS[code])}
          </button>
        );
      })}
    </div>
  );
}
