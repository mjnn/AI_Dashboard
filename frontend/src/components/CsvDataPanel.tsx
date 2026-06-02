import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

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

function UploadSpinner({ label }: { label: string }) {
  return (
    <div className="relative h-9 w-9 shrink-0" role="status" aria-label={label}>
      <div className="absolute inset-0 rounded-full border-2 border-cyan-100" />
      <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-cyan-600" />
    </div>
  );
}

export default function CsvDataPanel({ disabled = false, onPoolChange }: CsvDataPanelProps) {
  const { t } = useTranslation();
  const [files, setFiles] = useState<CsvFileInfo[]>([]);
  const [totalRowsHint, setTotalRowsHint] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadingFile, setUploadingFile] = useState<{
    name: string;
    size: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCsvFiles();
      setFiles(data.files);
      if (data.total === 0) {
        setTotalRowsHint(t("csv.emptyPool"));
      } else if (data.default_filename) {
        setTotalRowsHint(
          t("csv.poolSummaryDefault", {
            count: data.total,
            name: data.default_filename,
          })
        );
      } else {
        setTotalRowsHint(t("csv.poolSummary", { count: data.total }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("csv.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const handleUpload = async (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file || disabled || uploading) {
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError(t("csv.pickCsv"));
      return;
    }
    if (file.size > MAX_CSV_UPLOAD_BYTES) {
      setError(t("csv.tooLarge"));
      return;
    }

    setUploading(true);
    setUploadingFile({ name: file.name, size: file.size });
    setError(null);
    setSuccess(null);
    try {
      const result = await api.uploadCsv(file);
      setFiles(result.pool.files);
      setTotalRowsHint(t("csv.poolSummary", { count: result.pool.total }));
      setSuccess(result.message);
      onPoolChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("csv.uploadFailed"));
    } finally {
      setUploading(false);
      setUploadingFile(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (filename: string) => {
    if (disabled || uploading) {
      return;
    }
    if (!window.confirm(t("csv.confirmRemove", { name: filename }))) {
      return;
    }
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.deleteCsv(filename);
      setFiles(result.files);
      setTotalRowsHint(t("csv.poolSummary", { count: result.total }));
      setSuccess(t("csv.removed", { name: filename }));
      onPoolChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("csv.deleteFailed"));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="glass-panel relative p-4">
      {uploadingFile && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center rounded-[inherit] bg-white/75 backdrop-blur-[2px]"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="mx-4 flex max-w-sm flex-col items-center rounded-xl border border-cyan-100 bg-white px-6 py-5 shadow-lg">
            <UploadSpinner label={t("csv.uploadingAria")} />
            <p className="mt-3 text-sm font-medium text-slate-800">{t("csv.uploadTitle")}</p>
            <p
              className="mt-1 max-w-full truncate text-xs text-slate-500"
              title={uploadingFile.name}
            >
              {uploadingFile.name}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              {formatBytes(uploadingFile.size)}
              {uploadingFile.size > 10 * 1024 * 1024 ? t("csv.largeFileHint") : ""}
            </p>
            <div className="mt-3 h-1 w-40 overflow-hidden rounded-full bg-cyan-100">
              <div className="h-full w-1/3 animate-[upload-indeterminate_1.2s_ease-in-out_infinite] rounded-full bg-cyan-500" />
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-800">{t("csv.title")}</p>
          <p className="text-xs text-slate-500">
            {loading ? t("csv.loading") : totalRowsHint}
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
            className="inline-flex items-center gap-2 rounded-lg border border-cyan-600/30 bg-cyan-50 px-3 py-1.5 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading && uploadingFile ? (
              <>
                <span className="relative inline-block h-4 w-4 shrink-0">
                  <span className="absolute inset-0 rounded-full border border-cyan-200" />
                  <span className="absolute inset-0 animate-spin rounded-full border border-transparent border-t-cyan-600" />
                </span>
                {t("csv.uploading")}
              </>
            ) : (
              t("csv.upload")
            )}
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
                title={t("csv.removeTitle")}
              >
                {t("csv.remove")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-2 text-[11px] text-slate-400">{t("csv.footnote")}</p>
    </div>
  );
}
