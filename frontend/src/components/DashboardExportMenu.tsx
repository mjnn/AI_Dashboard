import { useRef, useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";

import type { AnalysisResponse } from "../types";
import {
  exportDashboard,
  type DashboardExportFormat,
} from "../utils/dashboardExport";

const FORMAT_OPTIONS: { id: DashboardExportFormat; label: string }[] = [
  { id: "html", label: "HTML" },
  { id: "pdf", label: "PDF" },
  { id: "png", label: "PNG" },
  { id: "jpg", label: "JPG" },
];

interface DashboardExportMenuProps {
  response: AnalysisResponse;
  exportRootRef: RefObject<HTMLElement | null>;
}

export default function DashboardExportMenu({
  response,
  exportRootRef,
}: DashboardExportMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<DashboardExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const title =
    response.presentation?.headline ??
    response.plan.matched_event ??
    "AI_座舱埋点看板";

  const handleExport = async (format: DashboardExportFormat) => {
    const root = exportRootRef.current;
    if (!root || busy) {
      return;
    }
    setBusy(format);
    setError(null);
    try {
      await exportDashboard(root, format, title);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("export.failed"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        disabled={Boolean(busy)}
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-white disabled:opacity-50"
        aria-expanded={open}
      >
        {busy
          ? t("export.busy", { format: busy.toUpperCase() })
          : t("export.label")}
      </button>

      {open && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default"
            aria-label={t("export.closeMenu")}
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-50 mt-2 w-40 rounded-xl border border-slate-200/90 bg-white p-1.5 shadow-xl">
            {FORMAT_OPTIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void handleExport(item.id)}
                className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
              >
                <span>{item.label}</span>
                {busy === item.id && (
                  <span className="text-[10px] text-slate-400">...</span>
                )}
              </button>
            ))}
          </div>
        </>
      )}

      {error && (
        <p className="absolute right-0 top-full z-50 mt-1 whitespace-nowrap text-xs text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
