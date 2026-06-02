import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

const BAR_DELAYS = ["0s", "0.15s", "0.42s", "0.08s", "0.55s", "0.28s", "0.63s"];
const BAR_DURATIONS = ["1.05s", "1.35s", "0.95s", "1.2s", "1.1s", "1.45s", "0.88s"];
const TIP_INTERVALS_MS = [2200, 3400, 2800, 4100, 2600, 3800];

function ChartForgeVisual() {
  return (
    <div className="chart-forge-stage" aria-hidden>
      <div className="chart-forge-aurora chart-forge-aurora-a" />
      <div className="chart-forge-aurora chart-forge-aurora-b" />
      <div className="chart-forge-ring" />
      <div className="chart-forge-orbit">
        <span className="chart-forge-dot chart-forge-dot-1" />
        <span className="chart-forge-dot chart-forge-dot-2" />
        <span className="chart-forge-dot chart-forge-dot-3" />
      </div>
      <div className="chart-forge-scan" />
      <div className="chart-forge-bars">
        {BAR_DELAYS.map((delay, index) => (
          <span
            key={index}
            className="chart-forge-bar"
            style={{
              animationDelay: delay,
              animationDuration: BAR_DURATIONS[index],
            }}
          />
        ))}
      </div>
      <svg className="chart-forge-sparkline" viewBox="0 0 120 40" preserveAspectRatio="none">
        <path
          className="chart-forge-spark-path"
          d="M0,32 C12,28 18,8 30,18 S48,36 60,12 S78,4 90,22 S108,30 120,8 L120,40 L0,40 Z"
        />
      </svg>
    </div>
  );
}

export default function LoadingState() {
  const { t, i18n } = useTranslation();
  const tips = useMemo(() => {
    const raw = t("loading.tips", { returnObjects: true });
    return Array.isArray(raw) ? (raw as string[]) : [t("loading.waitHint")];
  }, [t, i18n.language]);

  const [tipIndex, setTipIndex] = useState(0);
  const [tipVisible, setTipVisible] = useState(true);

  useEffect(() => {
    setTipIndex(0);
    setTipVisible(true);
    let cancelled = false;
    let intervalIdx = 0;

    const scheduleNext = () => {
      const wait = TIP_INTERVALS_MS[intervalIdx % TIP_INTERVALS_MS.length];
      intervalIdx += 1;
      return window.setTimeout(() => {
        if (cancelled) {
          return;
        }
        setTipVisible(false);
        window.setTimeout(() => {
          if (cancelled) {
            return;
          }
          setTipIndex((prev) => (prev + 1) % tips.length);
          setTipVisible(true);
          timerId = scheduleNext();
        }, 280);
      }, wait);
    };

    let timerId = scheduleNext();
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [tips.length, i18n.language]);

  const activeTip = tips[tipIndex] ?? tips[0];

  return (
    <div
      className="chart-forge-panel overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="relative px-6 pb-6 pt-8 sm:px-10 sm:pb-8 sm:pt-10">
        <ChartForgeVisual />

        <div className="relative z-10 mt-8 text-center">
          <p className="text-base font-semibold tracking-tight text-slate-800 sm:text-lg">
            {t("loading.rendering")}
          </p>
          <p
            className={`mt-2 min-h-[1.25rem] text-sm text-slate-500 transition-all duration-300 ${
              tipVisible ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
            }`}
          >
            {activeTip}
          </p>
        </div>

        <div className="relative z-10 mt-6 flex justify-center gap-1.5">
          {tips.map((_, index) => (
            <span
              key={index}
              className={`h-1 rounded-full transition-all duration-500 ${
                index === tipIndex
                  ? "w-6 bg-gradient-to-r from-cyan-500 to-violet-500"
                  : "w-1.5 bg-slate-200"
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
