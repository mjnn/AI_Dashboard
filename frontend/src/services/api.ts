import i18n, { getApiLocale } from "../i18n/config";
import type { AppLocale } from "../i18n/types";
import type {
  AnalysisModePreference,
  AnalysisResponse,
  CsvFilesResponse,
  CsvUploadResponse,
  DictionaryEventDetail,
  DictionaryEventUpdate,
  DictionaryEventUpdateResponse,
  DictionaryTestResponse,
  DictionaryTreeResponse,
  EventsListResponse,
  LlmSettingsResponse,
  LlmSettingsUpdate,
  RecommendationsResponse,
} from "../types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const RAW_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/** 拼接 API 根路径；避免 VITE_API_BASE 含 /api 时与 /api/xxx 路径重复 */
function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  let base = RAW_BASE;
  if (base.endsWith("/api") && normalized.startsWith("/api/")) {
    base = base.slice(0, -4);
  }
  return `${base}${normalized}`;
}

const REQUEST_TIMEOUT_MS = 300_000;
const UPLOAD_TIMEOUT_MS = 600_000;
export const MAX_CSV_UPLOAD_BYTES = 200 * 1024 * 1024;

async function parseErrorBody(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as Record<string, unknown>;
    if (typeof body.message === "string") {
      return body.message;
    }
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return JSON.stringify(body.detail);
    }
  } catch {
    if (text) {
      return text.slice(0, 200);
    }
  }
  return i18n.t("api.requestFailed", { status: response.status });
}

async function request<T>(
  path: string,
  options?: RequestInit & { signal?: AbortSignal }
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const signal = options?.signal ?? controller.signal;

  try {
    const response = await fetch(apiUrl(path), {
      ...options,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const message = await parseErrorBody(response);
      throw new ApiError(message, response.status);
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      const snippet = (await response.clone().text()).trimStart().slice(0, 80);
      throw new ApiError(
        snippet.startsWith("<!")
          ? i18n.t("api.notJson", {
              defaultValue:
                "API 返回了 HTML 而非 JSON，请检查 VITE_API_BASE 与后端是否已启动",
            })
          : i18n.t("api.notJson", { defaultValue: "API 响应不是 JSON" }),
        502
      );
    }

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(i18n.t("api.timeout"), 408);
    }
    throw new ApiError(
      err instanceof Error ? err.message : i18n.t("api.network"),
      0
    );
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export const api = {
  analyze: (
    query: string,
    analysisMode: AnalysisModePreference = "auto",
    signal?: AbortSignal,
    locale: AppLocale = getApiLocale()
  ) =>
    request<AnalysisResponse>("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        query,
        analysis_mode: analysisMode,
        locale,
      }),
      signal,
    }),

  listEvents: (signal?: AbortSignal) =>
    request<EventsListResponse>("/api/events", { signal }),

  getRecommendations: (signal?: AbortSignal, locale: AppLocale = getApiLocale()) =>
    request<RecommendationsResponse>(
      `/api/recommendations?locale=${encodeURIComponent(locale)}`,
      { signal }
    ),

  listCsvFiles: (signal?: AbortSignal) =>
    request<CsvFilesResponse>("/api/csv-files", { signal }),

  uploadCsv: async (file: File, signal?: AbortSignal): Promise<CsvUploadResponse> => {
    if (file.size > MAX_CSV_UPLOAD_BYTES) {
      throw new ApiError(i18n.t("api.fileTooLarge"), 422);
    }
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
    const abortSignal = signal ?? controller.signal;
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch(apiUrl("/api/csv-files/upload"), {
        method: "POST",
        body: form,
        signal: abortSignal,
      });
      if (!response.ok) {
        const message = await parseErrorBody(response);
        throw new ApiError(message, response.status);
      }
      return (await response.json()) as CsvUploadResponse;
    } catch (err) {
      if (err instanceof ApiError) {
        throw err;
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new ApiError(i18n.t("api.uploadTimeout"), 408);
      }
      throw new ApiError(
        err instanceof Error ? err.message : i18n.t("api.uploadFailed"),
        0
      );
    } finally {
      window.clearTimeout(timeoutId);
    }
  },

  deleteCsv: (filename: string, signal?: AbortSignal) =>
    request<CsvFilesResponse>(`/api/csv-files/${encodeURIComponent(filename)}`, {
      method: "DELETE",
      signal,
    }),

  getDictionaryTree: (signal?: AbortSignal) =>
    request<DictionaryTreeResponse>("/api/dictionary", { signal }),

  getDictionaryEvent: (eventName: string, signal?: AbortSignal) =>
    request<DictionaryEventDetail>(
      `/api/dictionary/events/${encodeURIComponent(eventName)}`,
      { signal }
    ),

  updateDictionaryEvent: (
    eventName: string,
    body: DictionaryEventUpdate,
    signal?: AbortSignal
  ) =>
    request<DictionaryEventUpdateResponse>(
      `/api/dictionary/events/${encodeURIComponent(eventName)}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
        signal,
      }
    ),

  testDictionaryEvent: (
    eventName: string,
    csvLabels?: string[],
    signal?: AbortSignal
  ) =>
    request<DictionaryTestResponse>("/api/dictionary/test-event", {
      method: "POST",
      body: JSON.stringify({
        event_name: eventName,
        csv_labels: csvLabels,
      }),
      signal,
    }),

  getLlmSettings: (signal?: AbortSignal) =>
    request<LlmSettingsResponse>("/api/settings/llm", { signal }),

  updateLlmSettings: (body: LlmSettingsUpdate, signal?: AbortSignal) =>
    request<LlmSettingsResponse>("/api/settings/llm", {
      method: "PUT",
      body: JSON.stringify(body),
      signal,
    }),
};
