import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../services/api";
import type { DictionaryEventDetail, DictionaryModuleNode, DictionaryTestResponse } from "../types";
import DictionaryEventEditor from "./DictionaryEventEditor";

interface DictionaryPanelProps {
  disabled?: boolean;
}

function filterModules(
  modules: DictionaryModuleNode[],
  keyword: string
): DictionaryModuleNode[] {
  const q = keyword.trim().toLowerCase();
  if (!q) {
    return modules;
  }
  return modules
    .map((module) => ({
      ...module,
      events: module.events.filter(
        (event) =>
          event.name.toLowerCase().includes(q) ||
          event.condition.toLowerCase().includes(q) ||
          event.data_id.toLowerCase().includes(q)
      ),
    }))
    .filter((module) => module.events.length > 0);
}

export default function DictionaryPanel({ disabled = false }: DictionaryPanelProps) {
  const [modules, setModules] = useState<DictionaryModuleNode[]>([]);
  const [meta, setMeta] = useState({ source: "", description: "", total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [detail, setDetail] = useState<DictionaryEventDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [testResult, setTestResult] = useState<DictionaryTestResponse | null>(null);

  const loadTree = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDictionaryTree();
      setModules(data.modules);
      setMeta({
        source: data.source,
        description: data.description,
        total: data.total_events,
      });
      const firstModule = data.modules[0];
      if (firstModule) {
        setExpanded((prev) => ({ ...prev, [firstModule.name]: true }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载字典失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTree();
  }, [loadTree]);

  const filteredModules = useMemo(
    () => filterModules(modules, search),
    [modules, search]
  );

  const loadDetail = useCallback(async (eventName: string) => {
    setSelectedEvent(eventName);
    setDetailLoading(true);
    setTestResult(null);
    setError(null);
    try {
      const data = await api.getDictionaryEvent(eventName);
      setDetail(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载事件详情失败");
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const toggleModule = (name: string) => {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  return (
    <div className="glass-panel overflow-hidden p-0">
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-medium text-slate-800">埋点字典</p>
        <p className="mt-0.5 text-xs text-slate-500">
          {loading
            ? "加载中..."
            : `共 ${meta.total} 个事件${meta.source ? ` · ${meta.source}` : ""}`}
        </p>
        {meta.description && (
          <p className="mt-1 line-clamp-2 text-[11px] text-slate-400">{meta.description}</p>
        )}
      </div>

      {error && <p className="px-4 py-2 text-xs text-red-500">{error}</p>}

      <div className="grid min-h-[520px] grid-cols-1 lg:grid-cols-[minmax(240px,320px)_1fr]">
        <aside className="border-b border-slate-100 lg:border-b-0 lg:border-r">
          <div className="p-3">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索事件名、Data ID、触发条件..."
              className="w-full rounded-lg border border-slate-200 bg-white/80 px-3 py-2 text-sm text-slate-700 outline-none ring-violet-200 focus:ring-2"
              disabled={loading || disabled}
            />
          </div>
          <div className="max-h-[460px] overflow-y-auto px-2 pb-3">
            {!loading && filteredModules.length === 0 && (
              <p className="px-2 py-4 text-center text-xs text-slate-400">无匹配事件</p>
            )}
            {filteredModules.map((module) => {
              const open = expanded[module.name] ?? false;
              return (
                <div key={module.name} className="mb-1">
                  <button
                    type="button"
                    onClick={() => toggleModule(module.name)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <span className="text-[10px] text-slate-400">{open ? "▼" : "▶"}</span>
                    <span className="truncate">{module.name}</span>
                    <span className="ml-auto text-[11px] text-slate-400">
                      {module.events.length}
                    </span>
                  </button>
                  {open && (
                    <ul className="ml-4 border-l border-slate-100 pl-2">
                      {module.events.map((event) => {
                        const active = selectedEvent === event.name;
                        return (
                          <li key={event.name}>
                            <button
                              type="button"
                              disabled={disabled}
                              onClick={() => void loadDetail(event.name)}
                              className={`mt-0.5 w-full truncate rounded-md px-2 py-1.5 text-left text-xs transition ${
                                active
                                  ? "bg-violet-50 font-medium text-violet-800"
                                  : "text-slate-600 hover:bg-slate-50"
                              }`}
                              title={event.name}
                            >
                              {event.name}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        <section className="min-h-[320px] p-4">
          {!selectedEvent && !detailLoading && (
            <div className="flex h-full min-h-[280px] items-center justify-center text-sm text-slate-400">
              从左侧选择事件，编辑口径并测试 CSV 匹配
            </div>
          )}
          {detailLoading && (
            <div className="flex h-full min-h-[280px] items-center justify-center text-sm text-slate-400">
              加载事件详情...
            </div>
          )}
          {selectedEvent && detail && !detailLoading && (
            <DictionaryEventEditor
              key={selectedEvent}
              eventName={selectedEvent}
              detail={detail}
              disabled={disabled}
              testResult={testResult}
              onTestResult={setTestResult}
              onSaved={(updated) => {
                setDetail(updated);
                void loadTree();
              }}
            />
          )}
        </section>
      </div>
    </div>
  );
}
