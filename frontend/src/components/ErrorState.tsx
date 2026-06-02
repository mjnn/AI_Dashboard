import { useTranslation } from "react-i18next";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

function classifyError(
  message: string,
  t: (key: string) => string
): { title: string; detail: string } {
  if (
    message.includes("404") ||
    message.includes("不存在") ||
    message.includes("not found") ||
    message.toLowerCase().includes("nicht gefunden")
  ) {
    return {
      title: t("error.dataNotFoundTitle"),
      detail: t("error.dataNotFoundDetail"),
    };
  }

  if (
    message.includes("DeepSeek") ||
    message.includes("API Key") ||
    message.includes("校验") ||
    message.includes("白名单") ||
    message.includes("分析计划") ||
    message.toLowerCase().includes("analysis plan")
  ) {
    return {
      title: t("error.planFailedTitle"),
      detail: message,
    };
  }

  const lower = message.toLowerCase();
  if (
    lower.includes("fetch") ||
    lower.includes("network") ||
    lower.includes("连接") ||
    lower.includes("verbindung") ||
    lower.includes("timeout") ||
    lower.includes("超时") ||
    lower.includes("zeitüberschreitung") ||
    lower.includes("abort")
  ) {
    return {
      title: t("error.networkTitle"),
      detail: t("error.networkDetail"),
    };
  }

  if (message.startsWith("[") && message.includes("type")) {
    return {
      title: t("error.invalidRequestTitle"),
      detail: t("error.invalidRequestDetail"),
    };
  }

  return {
    title: t("error.genericTitle"),
    detail: message,
  };
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  const { t } = useTranslation();
  const { title, detail } = classifyError(message, t);

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-100 text-xs font-bold text-red-600">
          !
        </span>
        <div className="flex-1">
          <p className="text-sm font-semibold text-red-700">{title}</p>
          <p className="mt-1 text-sm text-red-600/90">{detail}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700"
            >
              {t("error.retry")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
