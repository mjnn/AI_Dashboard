import type {
  AnalysisModePreference,
  AnalysisResponse,
  EventsListResponse,
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

const BASE_URL = import.meta.env.VITE_API_BASE ?? "";
const REQUEST_TIMEOUT_MS = 120_000;

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
  return `请求失败 (${response.status})`;
}

async function request<T>(
  path: string,
  options?: RequestInit & { signal?: AbortSignal }
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const signal = options?.signal ?? controller.signal;

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
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

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("请求超时，请稍后重试", 408);
    }
    throw new ApiError(
      err instanceof Error ? err.message : "网络连接失败",
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
    signal?: AbortSignal
  ) =>
    request<AnalysisResponse>("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        query,
        analysis_mode: analysisMode,
      }),
      signal,
    }),

  listEvents: (signal?: AbortSignal) =>
    request<EventsListResponse>("/api/events", { signal }),

  getRecommendations: (signal?: AbortSignal) =>
    request<RecommendationsResponse>("/api/recommendations", { signal }),
};
