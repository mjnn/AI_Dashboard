import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, MAX_CSV_UPLOAD_BYTES } from "../services/api";
import type { CsvFileInfo } from "../types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface CsvDataPanelProps {
  disabled?: boolean;
  onPoolChange?: () => void;
}

export default function CsvDataPanel({ disabled = false, onPoolChange }: CsvDataPanelProps) {
  const [files, setFiles] = useState<CsvFileInfo[]>([]);
  const [totalRowsHint, setTotalRowsHint] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCsvFiles();
      setFiles(data.files);
      setTotalRowsHint(
        data.total === 0
          ? "暂无 CSV，请上传"
          : `数据池 ${data.total} 个文件${data.default_filename ? ` · 默认 ${data.default_filename}` : ""}`
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载数据文件失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const handleUpload = async (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file || disabled || uploading) {
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("请选择 .csv 文件");
      return;
    }
    if (file.size > MAX_CSV_UPLOAD_BYTES) {
      setError("文件过大，单文件上限 200 MB");
      return;
    }

    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.uploadCsv(file);
      setFiles(result.pool.files);
      setTotalRowsHint(`数据池 ${result.pool.total} 个文件`);
      setSuccess(result.message);
      onPoolChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (filename: string) => {
    if (disabled || uploading) {
      return;
    }
    if (!window.confirm(`确定从数据池移除 ${filename}？`)) {
      return;
    }
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.deleteCsv(filename);
      setFiles(result.files);
      setTotalRowsHint(`数据池 ${result.total} 个文件`);
      setSuccess(`已移除 ${filename}`);
      onPoolChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="glass-panel p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-800">数据池 CSV</p>
          <p className="text-xs text-slate-500">
            {loading ? "加载中..." : totalRowsHint}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            disabled={disabled || uploading}
            onChange={(e) => void handleUpload(e.target.files)}
          />
          <button
            type="button"
            disabled={disabled || uploading}
            onClick={() => inputRef.current?.click()}
            className="rounded-lg border border-cyan-600/30 bg-cyan-50 px-3 py-1.5 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? "处理中..." : "上传 CSV"}
          </button>
        </div>
      </div>

      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      {success && <p className="mt-2 text-xs text-emerald-600">{success}</p>}

      {!loading && files.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-100 bg-white/60">
          {files.map((file) => (
            <li
              key={file.filename}
              className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
            >
              <span className="truncate text-slate-700" title={file.filename}>
                {file.filename}
              </span>
              <span className="shrink-0 text-xs text-slate-400">
                {formatBytes(file.size_bytes)}
              </span>
              <button
                type="button"
                disabled={disabled || uploading}
                onClick={() => void handleDelete(file.filename)}
                className="shrink-0 text-xs text-slate-400 transition hover:text-red-500 disabled:opacity-50"
                title="从数据池移除"
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-2 text-[11px] text-slate-400">
        上传后自动合并进数据池，分析时将使用目录内全部 CSV · 单文件最大 200 MB
      </p>
    </div>
  );
}
