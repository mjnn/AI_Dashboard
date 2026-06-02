import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../services/api";

import type {

  DictionaryEventDetail,

  DictionaryTestResponse,

  EventAttribute,

} from "../types";



interface DictionaryEventEditorProps {

  eventName: string;

  detail: DictionaryEventDetail;

  disabled?: boolean;

  testResult: DictionaryTestResponse | null;

  onTestResult: (result: DictionaryTestResponse | null) => void;

  onSaved: (detail: DictionaryEventDetail) => void;

}



function cloneAttributes(attrs: EventAttribute[]): EventAttribute[] {

  return JSON.parse(JSON.stringify(attrs)) as EventAttribute[];

}



function extractCsvLabels(attributes: EventAttribute[]): string[] {

  const labels: string[] = [];

  for (const attr of attributes) {

    if (attr["事件的属性"] !== "eventname") {

      continue;

    }

    const desc = attr["属性值的描述"];

    if (Array.isArray(desc)) {

      for (const item of desc) {

        if (item && typeof item === "object" && "label" in item && item.label) {

          labels.push(String(item.label));

        }

      }

    } else if (typeof desc === "string" && desc.trim()) {

      labels.push(desc.trim());

    }

  }

  return [...new Set(labels)];

}



function setEventnameLabels(attributes: EventAttribute[], labels: string[]): EventAttribute[] {

  const next = cloneAttributes(attributes);

  let eventnameIdx = next.findIndex((a) => a["事件的属性"] === "eventname");

  if (eventnameIdx < 0) {

    next.unshift({

      事件的属性: "eventname",

      属性中文说明: "英文事件名",

      属性值的描述: [],

    });

    eventnameIdx = 0;

  }

  next[eventnameIdx] = {

    ...next[eventnameIdx],

    属性值的描述: labels.map((label, index) => ({ code: index, label })),

  };

  return next;

}



export default function DictionaryEventEditor({

  eventName,

  detail,

  disabled = false,

  testResult,

  onTestResult,

  onSaved,

}: DictionaryEventEditorProps) {

  const [condition, setCondition] = useState(detail.event["事件触发条件"] ?? "");

  const [dataId, setDataId] = useState(detail.event["事件Data_ID"] ?? "");

  const [attributes, setAttributes] = useState<EventAttribute[]>(

    cloneAttributes((detail.event["属性列表"] as EventAttribute[]) ?? [])

  );

  const [csvLabelsText, setCsvLabelsText] = useState("");

  const [busy, setBusy] = useState<"test" | "save" | null>(null);

  const [message, setMessage] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);



  useEffect(() => {

    setCondition(detail.event["事件触发条件"] ?? "");

    setDataId(detail.event["事件Data_ID"] ?? "");

    const attrs = cloneAttributes((detail.event["属性列表"] as EventAttribute[]) ?? []);

    setAttributes(attrs);

    setCsvLabelsText(extractCsvLabels(attrs).join("\n"));

    onTestResult(null);

    setMessage(null);

    setError(null);

  }, [detail, onTestResult]);



  const dirty = useMemo(() => {

    const originalLabels = extractCsvLabels(

      (detail.event["属性列表"] as EventAttribute[]) ?? []

    ).join("\n");

    return (

      condition !== (detail.event["事件触发条件"] ?? "") ||

      dataId !== (detail.event["事件Data_ID"] ?? "") ||

      csvLabelsText.trim() !== originalLabels.trim()

    );

  }, [condition, dataId, csvLabelsText, detail]);



  const parsedLabels = useMemo(

    () =>

      csvLabelsText

        .split(/[\n,]+/)

        .map((s) => s.trim())

        .filter(Boolean),

    [csvLabelsText]

  );



  const runTest = useCallback(async () => {

    setBusy("test");

    setError(null);

    setMessage(null);

    try {

      const result = await api.testDictionaryEvent(eventName, parsedLabels);

      onTestResult(result);

      if (result.total_matched_rows === 0) {

        setMessage("当前映射未命中 CSV 数据，可参考下方建议 label");

      } else {

        setMessage(`匹配 ${result.total_matched_rows.toLocaleString()} 条记录`);

      }

    } catch (err) {

      setError(err instanceof ApiError ? err.message : "测试失败");

      onTestResult(null);

    } finally {

      setBusy(null);

    }

  }, [eventName, onTestResult, parsedLabels]);



  const handleSave = async () => {

    setBusy("save");

    setError(null);

    setMessage(null);

    try {

      const nextAttributes = setEventnameLabels(attributes, parsedLabels);

      const result = await api.updateDictionaryEvent(eventName, {

        事件触发条件: condition,

        事件Data_ID: dataId,

        属性列表: nextAttributes,

      });

      setAttributes(nextAttributes);

      onSaved({ module: detail.module, event: result.event });

      setMessage(result.message);

      const testRes = await api.testDictionaryEvent(eventName, parsedLabels);
      onTestResult(testRes);

    } catch (err) {

      setError(err instanceof ApiError ? err.message : "保存失败");

    } finally {

      setBusy(null);

    }

  };



  const applySuggestion = (label: string) => {

    const current = new Set(parsedLabels);

    current.add(label);

    setCsvLabelsText([...current].join("\n"));

  };



  const updateAttribute = (index: number, patch: Partial<EventAttribute>) => {

    setAttributes((prev) =>

      prev.map((item, i) => (i === index ? { ...item, ...patch } : item))

    );

  };



  return (

    <div className="space-y-4">

      <div>

        <p className="text-xs text-slate-500">所属模块 · {detail.module || "—"}</p>

        <h3 className="mt-1 text-base font-semibold text-slate-800">{eventName}</h3>

      </div>



      <div className="grid gap-3 sm:grid-cols-2">

        <label className="block text-xs text-slate-600">

          事件触发条件

          <textarea

            value={condition}

            onChange={(e) => setCondition(e.target.value)}

            rows={3}

            disabled={disabled || busy !== null}

            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700"

          />

        </label>

        <label className="block text-xs text-slate-600">

          事件 Data ID

          <input

            value={dataId}

            onChange={(e) => setDataId(e.target.value)}

            disabled={disabled || busy !== null}

            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm text-slate-700"

          />

        </label>

      </div>



      <div>

        <div className="flex items-center justify-between gap-2">

          <label className="text-xs font-medium text-slate-700">

            CSV event 映射 label（每行一个，对应数据池 event 列取值）

          </label>

          {dirty && (

            <span className="text-[11px] text-amber-600">有未保存修改</span>

          )}

        </div>

        <textarea

          value={csvLabelsText}

          onChange={(e) => setCsvLabelsText(e.target.value)}

          rows={4}

          disabled={disabled || busy !== null}

          placeholder="carlog_entry"

          className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm text-slate-700"

        />

        <p className="mt-1 text-[11px] text-slate-400">

          口径不清楚时，先改 label 再点「测试匹配」，确认命中行数后再保存

        </p>

      </div>



      <div className="flex flex-wrap gap-2">

        <button

          type="button"

          disabled={disabled || busy !== null || parsedLabels.length === 0}

          onClick={() => void runTest()}

          className="rounded-lg border border-cyan-600/30 bg-cyan-50 px-3 py-1.5 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100 disabled:opacity-50"

        >

          {busy === "test" ? "测试中..." : "测试匹配"}

        </button>

        <button

          type="button"

          disabled={disabled || busy !== null || !dirty}

          onClick={() => void handleSave()}

          className="rounded-lg border border-violet-500/30 bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-800 transition hover:bg-violet-100 disabled:opacity-50"

        >

          {busy === "save" ? "保存中..." : "保存到字典"}

        </button>

      </div>



      {error && <p className="text-xs text-red-500">{error}</p>}

      {message && <p className="text-xs text-emerald-600">{message}</p>}



      {testResult && (

        <div className="rounded-xl border border-slate-100 bg-white/70 p-3">

          <p className="text-xs font-medium text-slate-700">匹配结果</p>

          <p className="mt-1 text-[11px] text-slate-500">

            数据池共 {testResult.pool_total_rows.toLocaleString()} 行 · event 列{" "}

            {testResult.event_column ?? "—"} · 已保存映射{" "}

            {testResult.saved_csv_labels.length

              ? testResult.saved_csv_labels.join(", ")

              : "无"}

          </p>

          {testResult.label_stats.length > 0 && (

            <table className="mt-2 w-full text-left text-xs">

              <thead>

                <tr className="text-slate-400">

                  <th className="py-1 pr-2">label</th>

                  <th className="py-1 pr-2">命中行数</th>

                  <th className="py-1">在数据池</th>

                </tr>

              </thead>

              <tbody>

                {testResult.label_stats.map((row) => (

                  <tr key={row.label} className="border-t border-slate-50 text-slate-700">

                    <td className="py-1 pr-2 font-mono">{row.label}</td>

                    <td className="py-1 pr-2">{row.row_count.toLocaleString()}</td>

                    <td className="py-1">{row.in_pool ? "是" : "否"}</td>

                  </tr>

                ))}

              </tbody>

            </table>

          )}

          {testResult.suggested_csv_labels.length > 0 && (

            <div className="mt-3">

              <p className="text-[11px] text-slate-500">数据池中的相近 event 建议：</p>

              <div className="mt-1 flex flex-wrap gap-1.5">

                {testResult.suggested_csv_labels.map((label) => (

                  <button

                    key={label}

                    type="button"

                    disabled={disabled || busy !== null}

                    onClick={() => applySuggestion(label)}

                    className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-600 hover:border-violet-300 hover:text-violet-700"

                  >

                    + {label}

                  </button>

                ))}

              </div>

            </div>

          )}

          {testResult.sample_rows.length > 0 && (

            <details className="mt-3">

              <summary className="cursor-pointer text-[11px] text-slate-500">

                查看样例行（{testResult.sample_rows.length}）

              </summary>

              <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-50 p-2 text-[10px] text-slate-600">

                {JSON.stringify(testResult.sample_rows, null, 2)}

              </pre>

            </details>

          )}

        </div>

      )}



      <details className="rounded-xl border border-slate-100 bg-white/50 p-3">

        <summary className="cursor-pointer text-xs font-medium text-slate-700">

          全部属性（{attributes.length}）

        </summary>

        <div className="mt-3 space-y-3">

          {attributes.map((attr, index) => (

            <div key={`${attr["事件的属性"]}-${index}`} className="rounded-lg border border-slate-100 p-2">

              <div className="grid gap-2 sm:grid-cols-2">

                <label className="text-[11px] text-slate-500">

                  属性名

                  <input

                    value={attr["事件的属性"]}

                    onChange={(e) =>

                      updateAttribute(index, { 事件的属性: e.target.value })

                    }

                    disabled={disabled || busy !== null}

                    className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 text-xs"

                  />

                </label>

                <label className="text-[11px] text-slate-500">

                  中文说明

                  <input

                    value={attr["属性中文说明"] ?? ""}

                    onChange={(e) =>

                      updateAttribute(index, { 属性中文说明: e.target.value })

                    }

                    disabled={disabled || busy !== null}

                    className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 text-xs"

                  />

                </label>

              </div>

              <label className="mt-2 block text-[11px] text-slate-500">

                属性值的描述（JSON）

                <textarea

                  value={JSON.stringify(attr["属性值的描述"] ?? "", null, 2)}

                  onChange={(e) => {

                    try {

                      const parsed = JSON.parse(e.target.value) as EventAttribute["属性值的描述"];

                      updateAttribute(index, { 属性值的描述: parsed });

                    } catch {

                      /* 编辑过程中允许临时无效 JSON */

                    }

                  }}

                  rows={3}

                  disabled={disabled || busy !== null}

                  className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 font-mono text-[11px]"

                />

              </label>

            </div>

          ))}

        </div>

      </details>

    </div>

  );

}

