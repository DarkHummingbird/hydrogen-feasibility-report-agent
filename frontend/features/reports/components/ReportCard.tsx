import Link from "next/link";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ReportSummary } from "@/lib/api/types";
import { formatDateTime, reportStatusText } from "@/lib/status";

const STATUS_TONE: Record<string, "neutral" | "info" | "wait" | "ok" | "error"> = {
  draft: "neutral",
  outline_ready: "wait",
  writing: "info",
  paused: "wait",
  done: "ok",
};

export function ReportCard({
  report,
  onDelete,
}: {
  report: ReportSummary;
  onDelete: (report: ReportSummary) => void;
}) {
  const tone = STATUS_TONE[report.status] ?? "neutral";
  return (
    <article className="transition-ui flex flex-col gap-3 rounded-card border border-hairline bg-surface p-6 hover:border-ink/20">
      <div className="flex items-start justify-between gap-3">
        <h3 className="line-clamp-2 min-w-0 text-[15px] font-semibold leading-6 text-ink">
          <Link href={`/reports/${report.id}/outline`} className="hover:text-primary">
            {report.title}
          </Link>
        </h3>
        <StatusBadge tone={tone}>{reportStatusText(report.status)}</StatusBadge>
      </div>

      <dl className="grid grid-cols-3 gap-2 border-t border-hairline pt-3 text-[12px] text-ink-muted">
        <div>
          <dt className="sr-only">章节数</dt>
          <dd>
            <span className="text-ink">{report.chapters_count || "—"}</span> 章
          </dd>
        </div>
        <div>
          <dt className="sr-only">字数</dt>
          <dd>
            目标 <span className="text-ink">{report.target_words.toLocaleString()}</span> 字
          </dd>
        </div>
        <div className="text-right">
          <dt className="sr-only">创建时间</dt>
          <dd>{formatDateTime(report.created_at)}</dd>
        </div>
      </dl>

      <div className="mt-auto flex items-center justify-between gap-2">
        <span className="text-[12px] text-ink-muted">正文 {report.words_total.toLocaleString()} 字</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onDelete(report)}
            className="transition-ui rounded-small px-2 py-1 text-[12px] text-ink-muted hover:bg-danger-tint hover:text-vermillion"
          >
            删除
          </button>
          <Link
            href={`/reports/${report.id}/outline`}
            className="transition-ui rounded-small border border-hairline px-3 py-1 text-[12px] text-ink hover:border-ink/40"
          >
            {report.status === "draft" ? "去生成大纲" : "打开"}
          </Link>
        </div>
      </div>
    </article>
  );
}

export function ReportListSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-40 animate-pulse rounded-card border border-hairline bg-surface" />
      ))}
    </div>
  );
}

export function CreateEntry() {
  return (
    <Link
      href="/reports/new"
      className="transition-ui inline-flex min-h-9 items-center gap-1.5 rounded-control border border-primary bg-primary px-3.5 text-[14px] font-medium text-white hover:bg-primary-hover"
    >
      创建报告
    </Link>
  );
}
