import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../services/api";
import type { DeepSeekModelId, DeepSeekModelOption } from "../types";

interface LlmModelSelectorProps {
  disabled?: boolean;
}

const MODEL_HINTS: Record<DeepSeekModelId, string> = {
  "deepseek-v4-flash": "响应更快，适合日常分析与推荐",
  "deepseek-v4-pro": "推理更准，适合复杂查询与口径说明",
};

export default function LlmModelSelector({ disabled = false }: LlmModelSelectorProps) {
  const [model, setModel] = useState<DeepSeekModelId>("deepseek-v4-flash");
  const [options, setOptions] = useState<DeepSeekModelOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getLlmSettings();
      setModel(data.model);
      setOptions(data.available_models);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载模型设置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const handleSelect = async (next: DeepSeekModelId) => {
    if (disabled || saving || next === model) {
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.updateLlmSettings({ model: next });
      setModel(data.model);
      setOptions(data.available_models);
      setSuccess("模型已切换，后续分析与推荐将使用新模型");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "切换模型失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mb-5 rounded-xl border border-slate-200/80 bg-white/90 p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">DeepSeek 模型</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            影响分析规划、智能推荐与看板文案生成
          </p>
        </div>
        {loading && <span className="text-xs text-slate-400">加载中…</span>}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {(options.length > 0
          ? options
          : ([
              { id: "deepseek-v4-flash", label: "DeepSeek V4 Flash（更快）", selected: true },
              { id: "deepseek-v4-pro", label: "DeepSeek V4 Pro（更准）", selected: false },
            ] as DeepSeekModelOption[])
        ).map((item) => {
          const active = model === item.id;
          return (
            <button
              key={item.id}
              type="button"
              disabled={disabled || saving || loading}
              onClick={() => void handleSelect(item.id)}
              className={`rounded-lg border px-3 py-2.5 text-left transition ${
                active
                  ? "border-violet-400 bg-violet-50/80 ring-1 ring-violet-200"
                  : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2.5 w-2.5 rounded-full ${
                    active ? "bg-violet-500" : "bg-slate-300"
                  }`}
                />
                <span className="text-sm font-medium text-slate-800">{item.label}</span>
              </div>
              <p className="mt-1 pl-4 text-xs text-slate-500">{MODEL_HINTS[item.id]}</p>
            </button>
          );
        })}
      </div>

      {saving && <p className="mt-2 text-xs text-violet-600">正在切换…</p>}
      {success && <p className="mt-2 text-xs text-emerald-600">{success}</p>}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </section>
  );
}
