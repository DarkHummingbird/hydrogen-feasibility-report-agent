"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { LoadingBlock, StateBlock } from "@/components/ui/StateBlock";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { OutlineTable } from "@/features/outline/components/OutlineTable";
import { confirmOutline, generateOutline, getReport, saveOutline } from "@/lib/api/reports";
import { isAppError } from "@/lib/api/client";
import type { OutlineChapterInput, Report } from "@/lib/api/types";
import { reportStatusText } from "@/lib/status";

const TOTAL_MAX = 18000;

const toInput = (report: Report): OutlineChapterInput[] =>
  report.chapters.map((chapter) => ({
    seq: chapter.seq,
    title: chapter.title,
    key_points: chapter.key_points ?? [],
    data_needed: chapter.data_needed ?? [],
    suggested_words: chapter.suggested_words,
  }));

export function OutlineView({ reportId }: { reportId: string }) {

  const [report, setReport] = useState<Report | null>(null);
  const [chapters, setChapters] = useState<OutlineChapterInput[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "generate" | "save" | "confirm">("");
  const [notice, setNotice] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  /** 供操作完成后刷新用（由事件处理器调用，不在 effect 里同步 setState）。 */
  const refresh = useCallback(async () => {
    const data = await getReport(reportId);
    setReport(data);
    setChapters(toInput(data));
    setError("");
  }, [reportId]);

  useEffect(() => {
    let alive = true;
    getReport(reportId)
      .then((data) => {
        if (!alive) return;
        setReport(data);
        setChapters(toInput(data));
        setError("");
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(isAppError(err) ? err.userMessage : "读取报告失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [reportId]);

  const total = chapters.reduce((sum, chapter) => sum + (chapter.suggested_words || 0), 0);
  const overLimit = total > TOTAL_MAX;
  const readOnly = report ? report.status !== "draft" && report.status !== "outline_ready" : false;

  const run = async (kind: "generate" | "save" | "confirm") => {
    setError("");
    setNotice("");
    setWarnings([]);
    setBusy(kind);
    try {
      if (kind === "generate") {
        const data = await generateOutline(reportId);
        setReport(data);
        setChapters(toInput(data));
        setWarnings(data.warnings ?? []);
        setNotice(`已生成 ${data.chapters.length} 章大纲`);
      } else if (kind === "save") {
        if (overLimit) {
          setError(`字数合计 ${total.toLocaleString()} 超过上限 18,000，全文不能超过 2 万字，请先删减`);
          return;
        }
        const data = await saveOutline(reportId, chapters);
        setReport(data);
        setChapters(toInput(data));
        setWarnings(data.warnings ?? []);
        setNotice("大纲已保存");
      } else {
        if (overLimit) {
          setError(`字数合计 ${total.toLocaleString()} 超过上限 18,000，不能开始写全文`);
          return;
        }
        await saveOutline(reportId, chapters);
        await confirmOutline(reportId);
        setNotice("已开始写全文（约 10–20 分钟）。进度页在阶段 3-3 提供，现在可以回首页看状态。");
        await refresh();
      }
    } catch (err) {
      setError(isAppError(err) ? err.userMessage : "操作失败，请稍后重试");
    } finally {
      setBusy("");
    }
  };

  if (loading) return <LoadingBlock label="正在读取报告与大纲…" />;

  if (error && !report) {
    return (
      <StateBlock
        tone="error"
        title={error}
        description="这份报告可能已被删除。"
        action={
          <Link href="/" className="text-[13px] text-primary hover:underline">
            返回报告列表
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] text-ink-muted">
            <Link href="/" className="hover:text-primary">
              报告
            </Link>
            <span className="mx-1.5">/</span>大纲
          </p>
          <h1 className="display mt-1 text-ink">{report?.title}</h1>
          <p className="mt-1 text-[13px] text-ink-muted">
            目标 {report?.target_words.toLocaleString()} 字 · 大纲合计{" "}
            <span className={overLimit ? "text-vermillion" : "text-ink"}>{total.toLocaleString()}</span>{" "}
            字 / 上限 18,000
            {report ? (
              <>
                {" "}
                · <StatusBadge tone={report.status === "done" ? "ok" : report.status === "draft" ? "neutral" : "wait"}>
                  {reportStatusText(report.status)}
                </StatusBadge>
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outlined" onClick={() => void run("generate")} disabled={busy !== "" || readOnly}>
            {busy === "generate" ? "生成中…" : chapters.length ? "重新生成" : "生成大纲"}
          </Button>
          <Button variant="outlined" onClick={() => void run("save")} disabled={busy !== "" || readOnly}>
            {busy === "save" ? "保存中…" : "保存大纲"}
          </Button>
          <Button onClick={() => void run("confirm")} disabled={busy !== "" || overLimit || readOnly}>
            {busy === "confirm" ? "正在启动…" : "确认大纲并写全文"}
          </Button>
        </div>
      </div>

      {notice ? (
        <div className="rounded-card border border-hairline bg-sky-tint px-4 py-3 text-[13px] text-primary">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div
          role="alert"
          className="rounded-card border border-hairline bg-danger-tint px-4 py-3 text-[13px] text-vermillion"
        >
          {error}
        </div>
      ) : null}
      {warnings.length > 0 ? (
        <div className="rounded-card border border-hairline bg-marigold-tint px-4 py-3 text-[13px] text-saffron-ink">
          <p className="font-medium">程序校验提示</p>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <Card>
        <CardTitle
          action={
            <span className="text-[12px] text-ink-muted">
              {readOnly ? "这份报告已开始写全文，大纲只读" : "改完记得点「保存大纲」"}
            </span>
          }
        >
          章节
        </CardTitle>
        {readOnly ? (
          <OutlineReadOnly chapters={chapters} />
        ) : (
          <OutlineTable chapters={chapters} onChange={setChapters} />
        )}
      </Card>

      <p className="text-[12px] leading-6 text-ink-muted">
        确认后系统会先从资料里提炼关键事实（不展示），再逐章「检索 → 写 → 控字数 → 审计 → 重写」，全程约 10–20 分钟。
        确认后不可撤回，但可以重新生成大纲后再写。
      </p>
    </div>
  );
}

function OutlineReadOnly({ chapters }: { chapters: OutlineChapterInput[] }) {
  return (
    <>
      <ul className="flex flex-col gap-3 md:hidden">
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
      <div className="hidden w-full max-w-full md:block">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-hairline text-left text-[12px] text-ink-muted">
            <th className="w-10 py-2.5 font-medium">章</th>
            <th className="py-2.5 pr-3 font-medium">标题</th>
            <th className="py-2.5 pr-3 font-medium">关键论点</th>
            <th className="py-2.5 pr-3 font-medium">所需数据</th>
            <th className="w-24 py-2.5 font-medium">建议字数</th>
          </tr>
        </thead>
        <tbody>
          {chapters.map((chapter, index) => (
            <tr key={index} className="border-b border-hairline/70 align-top last:border-b-0">
              <td className="py-3 text-ink-muted">{index + 1}</td>
              <td className="py-3 pr-3 text-ink">{chapter.title}</td>
              <td className="py-3 pr-3 text-ink-muted">{(chapter.key_points ?? []).join("；") || "—"}</td>
              <td className="py-3 pr-3 text-ink-muted">{(chapter.data_needed ?? []).join("、") || "—"}</td>
              <td className="py-3 text-ink-muted">{chapter.suggested_words}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}
