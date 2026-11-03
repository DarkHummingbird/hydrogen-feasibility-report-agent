import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportCard } from "@/features/reports/components/ReportCard";

const base = {
  id: "r1",
  title: "攀枝花氢能一期可研",
  target_words: 12000,
  chapters_count: 0,
  words_total: 0,
  created_at: "2026-11-03T06:52:40",
};

describe("报告卡片", () => {
  it("显示标题、状态与目标字数", () => {
    render(<ReportCard report={{ ...base, status: "outline_ready" }} onDelete={() => {}} />);
    expect(screen.getByText("攀枝花氢能一期可研")).toBeInTheDocument();
    expect(screen.getByText("待确认大纲")).toBeInTheDocument();
    expect(screen.getByText("12,000")).toBeInTheDocument();
  });

  it("未知状态不显示成已完成", () => {
    // @ts-expect-error 故意传未知状态，验证兜底
    render(<ReportCard report={{ ...base, status: "weird" }} onDelete={() => {}} />);
    expect(screen.getByText("未知状态")).toBeInTheDocument();
    expect(screen.queryByText("已完成")).not.toBeInTheDocument();
  });
});
