import { useEffect, useState } from "react";

export default function LoadingState() {
  const [phase, setPhase] = useState<1 | 2>(1);

  useEffect(() => {
    const timer = window.setTimeout(() => setPhase(2), 2500);
    return () => window.clearTimeout(timer);
  }, []);

  const message =
    phase === 1 ? "正在分析您的需求..." : "正在处理数据与生成图表...";

  return (
    <div className="flex flex-col items-center justify-center rounded-lg bg-white py-12 shadow-sm">
      <div className="relative h-10 w-10">
        <div className="absolute inset-0 rounded-full border-2 border-blue-100" />
        <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-blue-600" />
      </div>
      <p className="mt-4 text-sm font-medium text-gray-700">{message}</p>
      <div className="mt-3 flex gap-2">
        <span
          className={`h-1.5 w-8 rounded-full transition-colors ${
            phase === 1 ? "bg-blue-600" : "bg-blue-200"
          }`}
        />
        <span
          className={`h-1.5 w-8 rounded-full transition-colors ${
            phase === 2 ? "bg-blue-600" : "bg-blue-200"
          }`}
        />
      </div>
    </div>
  );
}
