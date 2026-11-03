/**
 * 后端状态 → 前端统一状态（手册 9.1；《前端适配声明》§4）。
 * 未知状态不静默当成成功或失败，统一落到 unknown 兜底。
 */
import type { JobStatus, ReportStatus } from "./api/types";

export type UiStatus =
  | "idle"
  | "submitting"
  | "queued"
  | "running"
  | "waiting_user"
  | "succeeded"
  | "partially_succeeded"
  | "failed"
  | "disconnected"
  | "loading"
  | "empty"
  | "not_found"
  | "unknown";

export const REPORT_STATUS_TEXT: Record<ReportStatus, string> = {
  draft: "草稿",
  outline_ready: "待确认大纲",
  writing: "写作中",
  paused: "已暂停",
  done: "已完成",
};

export function reportStatusText(status: string): string {
  return REPORT_STATUS_TEXT[status as ReportStatus] ?? "未知状态";
}

export function jobToUiStatus(job: JobStatus | null | undefined, manual = 0): UiStatus {
  switch (job) {
    case "pending":
      return "queued";
    case "running":
      return "running";
    case "paused":
      return "disconnected";
    case "failed":
      return "failed";
    case "succeeded":
      return manual > 0 ? "partially_succeeded" : "succeeded";
    default:
      return job === null ? "idle" : "unknown";
  }
}

export function formatDateTime(iso: string): string {
  if (!iso) return "—";
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
