import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useChartTheme } from "../context/ChartThemeContext";
import {
  CHART_PALETTE_PRESETS,
  CUSTOM_PALETTE_ID,
  isValidHexColor,
} from "../theme/chartPalettes";

export default function ChartThemePicker() {
  const { t } = useTranslation();
  const {
    presetId,
    customColors,
    colors,
    setPresetId,
    updateCustomColor,
    addCustomColor,
    removeCustomColor,
  } = useChartTheme();
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border border-slate-200/80 bg-white/80 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-white"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <span className="flex -space-x-1">
          {colors.slice(0, 5).map((color) => (
            <span
              key={color}
              className="inline-block h-3.5 w-3.5 rounded-full border border-white ring-1 ring-slate-200/80"
              style={{ backgroundColor: color }}
            />
          ))}
        </span>
        {t("chartTheme.label")}
      </button>

      {open && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default"
            aria-label={t("chartTheme.close")}
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-slate-200/90 bg-white p-4 shadow-xl">
            <p className="text-xs font-semibold text-slate-800">{t("chartTheme.paletteTitle")}</p>
            <p className="mt-0.5 text-[11px] text-slate-500">{t("chartTheme.paletteHint")}</p>

            <div className="mt-3 grid grid-cols-2 gap-2">
              {CHART_PALETTE_PRESETS.filter((p) => p.id !== CUSTOM_PALETTE_ID).map(
                (preset) => {
                  const selected = presetId === preset.id;
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => setPresetId(preset.id)}
                      className={`rounded-lg border px-2 py-2 text-left transition ${
                        selected
                          ? "border-violet-400 bg-violet-50 ring-1 ring-violet-200"
                          : "border-slate-100 hover:border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <span className="block text-[11px] font-medium text-slate-700">
                        {preset.name}
                      </span>
                      <span className="mt-1.5 flex flex-wrap gap-1">
                        {preset.colors.slice(0, 6).map((color) => (
                          <span
                            key={color}
                            className="h-3 w-3 rounded-full"
                            style={{ backgroundColor: color }}
                          />
                        ))}
                      </span>
                    </button>
                  );
                }
              )}
            </div>

            <button
              type="button"
              onClick={() => setPresetId(CUSTOM_PALETTE_ID)}
              className={`mt-2 w-full rounded-lg border px-2 py-2 text-left text-[11px] font-medium transition ${
                presetId === CUSTOM_PALETTE_ID
                  ? "border-violet-400 bg-violet-50 text-violet-800"
                  : "border-slate-100 text-slate-700 hover:bg-slate-50"
              }`}
            >
              {t("chartTheme.custom")}
            </button>

            {presetId === CUSTOM_PALETTE_ID && (
              <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                {customColors.map((color, index) => (
                  <div key={`custom-${index}`} className="flex items-center gap-2">
                    <input
                      type="color"
                      value={isValidHexColor(color) ? color : "#6366F1"}
                      onChange={(e) => updateCustomColor(index, e.target.value)}
                      className="h-8 w-10 cursor-pointer rounded border border-slate-200 bg-white p-0.5"
                    />
                    <input
                      type="text"
                      value={color}
                      onChange={(e) => updateCustomColor(index, e.target.value)}
                      className="flex-1 rounded border border-slate-200 px-2 py-1 text-xs font-mono text-slate-700"
                      spellCheck={false}
                    />
                    <button
                      type="button"
                      onClick={() => removeCustomColor(index)}
                      className="text-xs text-slate-400 hover:text-red-500"
                      title={t("chartTheme.removeColor")}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addCustomColor}
                  className="text-xs text-violet-600 hover:text-violet-800"
                >
                  {t("chartTheme.addColor")}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
