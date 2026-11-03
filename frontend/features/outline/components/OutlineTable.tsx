"use client";

import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { OutlineChapterInput } from "@/lib/api/types";

export function OutlineTable({
  chapters,
  onChange,
}: {
  chapters: OutlineChapterInput[];
  onChange: (next: OutlineChapterInput[]) => void;
}) {
  const update = (index: number, patch: Partial<OutlineChapterInput>) => {
    const next = chapters.map((chapter, i) => (i === index ? { ...chapter, ...patch } : chapter));
    onChange(next);
  };

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= chapters.length) return;
    const next = [...chapters];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  const remove = (index: number) => {
    onChange(chapters.filter((_, i) => i !== index));
  };

  const add = () => {
    onChange([
      ...chapters,
      { title: "新增章节", key_points: [""], data_needed: [""], suggested_words: 500 },
    ]);
  };

  if (chapters.length === 0) {
    return (
      <p className="py-8 text-center text-[13px] text-ink-muted">
        还没有大纲。点上方「生成大纲」，或直接「加一章」手写。
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="rounded-small bg-marigold-tint px-3 py-2 text-[12px] text-saffron-ink md:hidden">
        手机上可以先看大纲；改标题、论点、字数请在电脑上操作。
      </p>
      <div className="hidden w-full max-w-full md:block">
        <table className="w-full border-collapse align-top text-[13px]">
          <thead>
            <tr className="border-b border-hairline text-left text-[12px] text-ink-muted">
              <th className="w-10 py-2.5 font-medium">章</th>
              <th className="py-2.5 pr-3 font-medium">标题</th>
              <th className="py-2.5 pr-3 font-medium">关键论点（每行一条）</th>
              <th className="py-2.5 pr-3 font-medium">所需数据（每行一个）</th>
              <th className="w-24 py-2.5 pr-3 font-medium">建议字数</th>
              <th className="w-28 py-2.5 font-medium">
                <span className="sr-only">操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {chapters.map((chapter, index) => (
              <tr key={index} className="border-b border-hairline/70 align-top last:border-b-0">
                <td className="py-2.5 text-ink-muted">{index + 1}</td>
                <td className="py-2.5 pr-3">
                  <input
                    aria-label={`第 ${index + 1} 章标题`}
                    className="transition-ui w-full rounded-small border border-transparent bg-transparent px-1.5 py-1 text-[13px] text-ink hover:border-hairline focus:border-primary focus:outline-none"
                    value={chapter.title}
                    onChange={(event) => update(index, { title: event.target.value })}
                  />
                </td>
                <td className="py-2.5 pr-3">
                  <textarea
                    aria-label={`第 ${index + 1} 章关键论点`}
                    className="transition-ui min-h-[52px] w-full rounded-small border border-transparent bg-transparent px-1.5 py-1 text-[13px] leading-6 text-ink hover:border-hairline focus:border-primary focus:outline-none"
                    value={(chapter.key_points ?? []).join("\n")}
                    onChange={(event) =>
                      update(index, {
                        key_points: event.target.value
                          .split("\n")
                          .map((line) => line.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </td>
                <td className="py-2.5 pr-3">
                  <textarea
                    aria-label={`第 ${index + 1} 章所需数据`}
                    className="transition-ui min-h-[52px] w-full rounded-small border border-transparent bg-transparent px-1.5 py-1 text-[13px] leading-6 text-ink hover:border-hairline focus:border-primary focus:outline-none"
                    value={(chapter.data_needed ?? []).join("\n")}
                    onChange={(event) =>
                      update(index, {
                        data_needed: event.target.value
                          .split("\n")
                          .map((line) => line.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </td>
                <td className="py-2.5 pr-3">
                  <input
                    type="number"
                    min={100}
                    step={100}
                    aria-label={`第 ${index + 1} 章建议字数`}
                    className="transition-ui w-20 rounded-small border border-hairline px-1.5 py-1 text-[13px] text-ink focus:border-primary focus:outline-none"
                    value={chapter.suggested_words}
                    onChange={(event) =>
                      update(index, { suggested_words: Number(event.target.value) || 0 })
                    }
                  />
                </td>
                <td className="py-2.5">
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      aria-label={`上移第 ${index + 1} 章`}
                      className="transition-ui rounded-small p-1 text-ink-muted hover:bg-black/5 hover:text-ink"
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label={`下移第 ${index + 1} 章`}
                      className="transition-ui rounded-small p-1 text-ink-muted hover:bg-black/5 hover:text-ink"
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label={`删除第 ${index + 1} 章`}
                      className="transition-ui rounded-small p-1 text-ink-muted hover:bg-danger-tint hover:text-vermillion"
                      onClick={() => remove(index)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="flex flex-col gap-2 md:hidden">
        {chapters.map((chapter, index) => (
          <li key={index} className="rounded-card border border-hairline p-3">
            <p className="text-[13px] font-medium text-ink">
              {index + 1}. {chapter.title}
            </p>
            <p className="mt-1 text-[12px] text-ink-muted">
              论点：{(chapter.key_points ?? []).join("；") || "—"}
            </p>
            <p className="mt-1 text-[12px] text-ink-muted">
              数据：{(chapter.data_needed ?? []).join("、") || "—"} · 建议 {chapter.suggested_words} 字
            </p>
          </li>
        ))}
      </ul>
      <div className="hidden items-center justify-between gap-3 md:flex">
        <Button variant="outlined" onClick={add}>
          加一章
        </Button>
        <span className="text-[12px] text-ink-muted">
          共 {chapters.length} 章
        </span>
      </div>
    </div>
  );
}
