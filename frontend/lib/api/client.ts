/**
 * 统一 API 客户端（手册 12.1 / 12.3）。
 *
 * - 页面不拼接接口地址，也不各自解释错误；
 * - 后端错误结构固定 {"error": {"code", "message"}}，这里归一成 AppError；
 * - 网络错误 / 非 JSON 响应 / 后端未启动都转成可显示的 userMessage。
 */

export type AppError = {
  code: string;
  message: string;
  userMessage: string;
  retryable: boolean;
  status?: number;
};

const CODE_MESSAGES: Record<string, string> = {
  NOT_FOUND: "这条记录不存在或已被删除",
  INVALID_REQUEST: "填写的内容有问题，请检查后重试",
  INVALID_TARGET_WORDS: "目标字数超出范围（1,000–18,000）",
  TITLE_REQUIRED: "请填写报告标题",
  UNSUPPORTED_FORMAT: "格式不支持，请上传 PDF、Word、Markdown 或 TXT",
  FILE_TOO_LARGE: "文件超过大小上限",
  EMPTY_FILE: "文件是空的",
  NO_DOCUMENTS: "资料库还是空的，先去上传资料",
  NO_OUTLINE: "还没有大纲，先生成大纲",
  OUTLINE_TOO_LONG: "大纲字数合计超过 18,000，请先删减",
  MODEL_NOT_CONFIGURED: "还没有配置 DeepSeek API Key，请联系管理员",
  MODEL_FAILED: "模型调用失败，请稍后重试",
  OUTLINE_INVALID: "模型没有返回可用的大纲，请重试",
  JOB_RUNNING: "这份报告正在写，等它跑完",
  BACKEND_UNREACHABLE: "后端没有启动或网络不通",
  BACKEND_NOT_CONFIGURED: "没有配置后端地址",
};

const FALLBACK_MESSAGE = "出了点问题，请稍后重试；反复失败请把这段话发给开发";

function toAppError(code: string, message: string, status?: number): AppError {
  return {
    code,
    message,
    userMessage: CODE_MESSAGES[code] ?? message ?? FALLBACK_MESSAGE,
    retryable: status === undefined || status >= 500,
    status,
  };
}

export async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, headers, ...rest } = init;
  const finalHeaders = new Headers(headers);
  let body = rest.body;
  if (json !== undefined) {
    finalHeaders.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }

  let response: Response;
  try {
    response = await fetch(path, { ...rest, body, headers: finalHeaders, cache: "no-store" });
  } catch {
    throw toAppError("NETWORK_ERROR", "网络请求失败");
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const err = (payload as { error?: { code?: string; message?: string } } | null)?.error;
    throw toAppError(
      err?.code ?? `HTTP_${response.status}`,
      err?.message ?? `请求失败（HTTP ${response.status}）`,
      response.status,
    );
  }

  return payload as T;
}

export function isAppError(value: unknown): value is AppError {
  return typeof value === "object" && value !== null && "userMessage" in value;
}

export { toAppError, FALLBACK_MESSAGE };
