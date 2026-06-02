import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import Dashboard from "./components/Dashboard";
import ChartThemePicker from "./components/ChartThemePicker";
import DashboardExportMenu from "./components/DashboardExportMenu";
import DataManagementPage from "./components/DataManagementPage";
import ErrorState from "./components/ErrorState";
import InputPanel from "./components/InputPanel";
import LanguageSwitcher from "./components/LanguageSwitcher";
import LoadingState from "./components/LoadingState";
import { useAnalysis } from "./hooks/useAnalysis";

type AppView = "dashboard" | "data-management";

export default function App() {
  const { t } = useTranslation();
  const { status, result, error, execute, retry, reset } = useAnalysis();
  const [view, setView] = useState<AppView>("dashboard");
  const [poolVersion, setPoolVersion] = useState(0);
  const handlePoolChange = useCallback(() => {
    setPoolVersion((v) => v + 1);
  }, []);
  const isExploratory =
    result?.mode === "exploratory" || result?.mode === "comprehensive";
  const headline = result?.presentation?.headline ?? t("app.defaultTitle");
  const eventName = result?.plan.scope_label ?? result?.plan.matched_event;
  const scopeCount = result?.scope_events?.length ?? result?.plan.csv_event_filter?.length;
  const primaryCluster = result?.analysis_clusters?.find((c) => c.is_primary);
  const dashboardExportRef = useRef<HTMLDivElement>(null);

  if (view === "data-management") {
    return (
      <DataManagementPage
        analysisBusy={status === "loading"}
        onPoolChange={handlePoolChange}
        onClose={() => setView("dashboard")}
      />
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="dash-top shrink-0">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="dash-title">{headline}</h1>
            {result && (
              <div className="dash-meta">
                {t("app.scopeLabel")}：<strong>{primaryCluster?.name ?? eventName}</strong>
                {scopeCount != null && scopeCount > 1 && (
                  <>
                    {" "}
                    · <strong>{t("app.scopeEvents", { count: scopeCount })}</strong>
                  </>
                )}
                {result.execution.total_rows > 0 && (
                  <>
                    {" "}
                    · {t("app.rowCount", {
                      count: result.execution.total_rows.toLocaleString(),
                    })}
                  </>
                )}
              </div>
            )}
            {!result && <div className="dash-meta">{t("app.metaHint")}</div>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <LanguageSwitcher />
            <button
              type="button"
              onClick={() => setView("data-management")}
              className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-white"
            >
              {t("app.dataManagement")}
            </button>
            <ChartThemePicker />
          </div>
        </div>
      </header>

      <main
        className={`relative z-20 mx-auto w-full flex-1 px-6 pb-8 pt-5 ${
          isExploratory ? "max-w-[1400px]" : "max-w-6xl"
        }`}
      >
        <div className="relative isolate space-y-3">
          <InputPanel
            dataPoolVersion={poolVersion}
            onSubmit={(query, mode) => void execute(query, mode)}
            disabled={status === "loading"}
          />
        </div>

        {status === "loading" && (
          <div className="mt-5">
            <LoadingState />
          </div>
        )}

        {status === "error" && error && (
          <div className="mt-5">
            <ErrorState message={error} onRetry={retry} />
          </div>
        )}

        {status === "success" && result && (
          <div className="mt-5 space-y-4">
            <div className="flex flex-wrap items-center justify-end gap-3">
              <DashboardExportMenu response={result} exportRootRef={dashboardExportRef} />
              <button
                type="button"
                onClick={reset}
                className="text-sm font-medium text-dash-cyan transition hover:text-cyan-700"
              >
                {t("app.newAnalysis")}
              </button>
            </div>
            <div ref={dashboardExportRef} id="dashboard-export-root">
              <Dashboard response={result} />
            </div>
          </div>
        )}
      </main>

      <footer className="relative z-0 shrink-0 border-t border-slate-200/60 py-7 text-center text-[11px] text-dash-mut">
        {t("app.footer")}
      </footer>
    </div>
  );
}
