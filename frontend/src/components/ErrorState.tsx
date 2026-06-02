interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

function classifyError(message: string): { title: string; detail: string } {
  if (message.includes("404") || message.includes("不存在")) {
    return {
      title: "数据文件未找到",
      detail: "请检查 CSV_DATA_PATH 目录配置，并确保 data 目录内有 .csv 文件。",
    };
  }

  if (
    message.includes("DeepSeek") ||
    message.includes("API Key") ||
    message.includes("校验") ||
    message.includes("白名单") ||
    message.includes("分析计划")
  ) {
    return {
      title: "分析计划生成失败",
      detail: message,
    };
  }

  const lower = message.toLowerCase();
  if (
    lower.includes("fetch") ||
    lower.includes("network") ||
    lower.includes("连接") ||
    lower.includes("timeout") ||
    lower.includes("超时") ||
    lower.includes("abort")
  ) {
    return {
      title: "网络连接异常",
      detail: "无法连接分析服务，请确认后端已启动并重试。",
    };
  }

  if (message.startsWith("[") && message.includes("type")) {
    return {
      title: "请求参数无效",
      detail: "请检查输入内容后重试",
    };
  }

  return {
    title: "分析失败",
    detail: message,
  };
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  const { title, detail } = classifyError(message);

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
              重试
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
