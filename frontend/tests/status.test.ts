import { describe, expect, it } from "vitest";
import { formatDateTime, jobToUiStatus, reportStatusText } from "@/lib/status";

describe("后端状态 → 前端统一状态", () => {
  it("任务状态映射符合声明 §4", () => {
    expect(jobToUiStatus("pending")).toBe("queued");
    expect(jobToUiStatus("running")).toBe("running");
    expect(jobToUiStatus("paused")).toBe("disconnected");
    expect(jobToUiStatus("failed")).toBe("failed");
    expect(jobToUiStatus("succeeded", 0)).toBe("succeeded");
    expect(jobToUiStatus("succeeded", 2)).toBe("partially_succeeded");
    expect(jobToUiStatus(null)).toBe("idle");
  });

  it("未知状态落到兜底，不静默当成成功", () => {
    expect(jobToUiStatus(undefined)).toBe("unknown");
    expect(reportStatusText("weird_state")).toBe("未知状态");
    expect(reportStatusText("done")).toBe("已完成");
  });

  it("时间按本地时区展示", () => {
    expect(formatDateTime("2026-11-03T06:52:40")).toMatch(/^2026-11-03 \d{2}:\d{2}$/);
    expect(formatDateTime("")).toBe("—");
  });
});
