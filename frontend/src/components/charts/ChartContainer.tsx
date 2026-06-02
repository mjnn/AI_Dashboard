import type { ReactNode } from "react";

export function ChartContainer({
  title,
  children,
  hideTitle = false,
}: {
  title?: string;
  children: ReactNode;
  hideTitle?: boolean;
}) {
  return (
    <div className="min-h-[320px] bg-transparent p-2">
      {title && !hideTitle && (
        <h3 className="mb-3 text-sm font-bold text-slate-800">{title}</h3>
      )}
      {children}
    </div>
  );
}
