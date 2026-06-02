import type { AnalysisPlan } from "../types";

interface CaliberCardProps {
  plan: AnalysisPlan;
}

export default function CaliberCard({ plan }: CaliberCardProps) {
  return (
    <div className="glass-panel px-4 py-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-dash-mut">
        统计口径
      </h3>
      <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
        {plan.statistical_caliber.description}
      </p>
    </div>
  );
}
