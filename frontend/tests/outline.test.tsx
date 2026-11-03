import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OutlineTable } from "@/features/outline/components/OutlineTable";

const chapters = [
  { title: "概述", key_points: ["概况"], data_needed: ["总投资"], suggested_words: 1000 },
  { title: "建设方案", key_points: ["方案"], data_needed: ["压力"], suggested_words: 800 },
];

describe("大纲表格", () => {
  it("显示章数与每章内容", () => {
    render(<OutlineTable chapters={chapters} onChange={() => {}} />);
    expect(screen.getByText("共 2 章")).toBeInTheDocument();
    expect(screen.getByDisplayValue("概述")).toBeInTheDocument();
    expect(screen.getByDisplayValue("总投资")).toBeInTheDocument();
  });

  it("改标题会回传新的章节列表", async () => {
    const onChange = vi.fn();
    render(<OutlineTable chapters={chapters} onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("第 1 章标题"), "改");
    expect(onChange).toHaveBeenCalled();
    const latest = onChange.mock.calls.at(-1)?.[0] as typeof chapters;
    expect(latest).toHaveLength(2);
    expect(latest[0].title).toContain("改");
  });

  it("上移会交换顺序", async () => {
    const onChange = vi.fn();
    render(<OutlineTable chapters={chapters} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("上移第 2 章"));
    const latest = onChange.mock.calls.at(-1)?.[0] as typeof chapters;
    expect(latest[0].title).toBe("建设方案");
    expect(latest[1].title).toBe("概述");
  });

  it("删除会移除对应章节", async () => {
    const onChange = vi.fn();
    render(<OutlineTable chapters={chapters} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("删除第 1 章"));
    const latest = onChange.mock.calls.at(-1)?.[0] as typeof chapters;
    expect(latest).toHaveLength(1);
    expect(latest[0].title).toBe("建设方案");
  });
});
