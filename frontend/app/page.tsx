"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { LoadingBlock, StateBlock } from "@/components/ui/StateBlock";
import { Button } from "@/components/ui/Button";
import { CreateEntry, ReportCard, ReportListSkeleton } from "@/features/reports/components/ReportCard";
import { deleteReport, listReports } from "@/lib/api/reports";
import { isAppError } from "@/lib/api/client";
import type { ReportSummary } from "@/lib/api/types";
import { useAsync } from "@/lib/hooks/useAsync";

function CreatedBanner() {
  const params = useSearchParams();
  if (params.get("created") !== "1") return null;
  return (
    <div className="mb-4 rounded-card border border-hairline bg-sky-tint px-4 py-3 text-[13px] text-primary">
      报告已创建。大纲页（生成大纲、编辑章节）在阶段 3-2 提供，当前可在列表里看到它的状态。
    </div>
  );
}

function HomeContent() {
  const { data, error, loading, reload } = useAsync(listReports);
  const items = data?.items ?? [];
  const [pendingDelete, setPendingDelete] = useState<ReportSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteReport(pendingDelete.id);
      setPendingDelete(null);
      reload();
    } catch (err) {
      setDeleteError(isAppError(err) ? err.userMessage : "删除失败，请稍后重试");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-ink">报告</h1>
          <p className="mt-1 text-[13px] text-ink-muted">
            {loading
              ? "正在加载…"
              : error
                ? "没能拿到报告列表（详见下方提示）"
                : `共 ${items.length} 份。创建报告后，先生成大纲再一键写全文。`}
          </p>
        </div>
        <CreateEntry />
      </div>

      <Suspense fallback={null}>
        <CreatedBanner />
      </Suspense>

      {loading ? <ReportListSkeleton /> : null}

      {!loading && error ? (
        <StateBlock
          tone="error"
          title={error.userMessage}
          description={
            <>
              后端可能没有启动。启动命令：
              <code className="ml-1 rounded-small bg-black/5 px-1.5 py-0.5 text-[12px]">cd backend &amp;&amp; .venv/bin/python -m uvicorn app.main:app --port 8010</code>
            </>
          }
          action={<Button onClick={() => void reload()}>重新加载</Button>}
        />
      ) : null}

      {!loading && !error && items.length === 0 ? (
        <StateBlock
          title="还没有报告"
          description="点右上「创建报告」，填标题和目标字数就能开始。"
          action={<CreateEntry />}
        />
      ) : null}

      {!loading && !error && items.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((report) => (
            <ReportCard key={report.id} report={report} onDelete={setPendingDelete} />
          ))}
        </div>
      ) : null}
      {pendingDelete ? (
        <div
          className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-report-title"
        >
          <div className="w-full max-w-md rounded-card border border-hairline bg-surface p-6">
            <h2 id="delete-report-title" className="text-[16px] font-semibold text-ink">
              删除这份报告？
            </h2>
            <p className="mt-2 text-[13px] leading-6 text-ink-muted">
              「{pendingDelete.title}」的大纲、正文与导出记录都会被删除，不能恢复。
            </p>
            {deleteError ? (
              <p role="alert" className="mt-2 text-[12px] text-vermillion">
                {deleteError}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outlined" onClick={() => setPendingDelete(null)} disabled={deleting}>
                保留
              </Button>
              <Button onClick={confirmDelete} disabled={deleting}>
                {deleting ? "正在删除…" : "删除"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <HomeContent />
    </Suspense>
  );
}
