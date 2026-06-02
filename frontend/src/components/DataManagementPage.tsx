import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import CsvDataPanel from "./CsvDataPanel";
import DictionaryPanel from "./DictionaryPanel";
import LanguageSwitcher from "./LanguageSwitcher";
import LlmModelSelector from "./LlmModelSelector";

export type DataManagementTab = "csv" | "dictionary";

interface DataManagementPageProps {
  onClose: () => void;
  onPoolChange?: () => void;
  analysisBusy?: boolean;
}

export default function DataManagementPage({
  onClose,
  onPoolChange,
  analysisBusy = false,
}: DataManagementPageProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<DataManagementTab>("csv");

  const tabs = useMemo(
    () =>
      [
        { id: "csv" as const, label: t("dataMgmt.tabCsv") },
        { id: "dictionary" as const, label: t("dataMgmt.tabDictionary") },
      ] satisfies { id: DataManagementTab; label: string }[],
    [t]
  );

  return (
    <div className="min-h-screen">
      <header className="dash-top">
        <div className="flex w-full flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="dash-title">{t("dataMgmt.title")}</h1>
            <p className="dash-meta">{t("dataMgmt.subtitle")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <LanguageSwitcher />
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-white"
            >
              {t("dataMgmt.back")}
            </button>
          </div>
        </div>
      </header>

      <div className="relative z-[1] mx-auto max-w-6xl px-6 pb-16 pt-5">
        <div className="mb-4 flex gap-2 border-b border-slate-200/80">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`border-b-2 px-4 py-2 text-sm font-medium transition ${
                tab === item.id
                  ? "border-violet-500 text-violet-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <LlmModelSelector disabled={analysisBusy} />

        {tab === "csv" && (
          <CsvDataPanel disabled={analysisBusy} onPoolChange={onPoolChange} />
        )}
        {tab === "dictionary" && <DictionaryPanel disabled={analysisBusy} />}
      </div>
    </div>
  );
}
