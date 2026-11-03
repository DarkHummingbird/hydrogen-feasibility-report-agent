"use client";

import { useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { LoadingBlock, StateBlock } from "@/components/ui/StateBlock";
import { DocumentList } from "@/features/documents/components/DocumentList";
import { UploadPanel } from "@/features/documents/components/UploadPanel";
import { deleteDocument, listDocuments } from "@/lib/api/documents";
import { isAppError } from "@/lib/api/client";
import { useAsync } from "@/lib/hooks/useAsync";
import type { DocumentItem } from "@/lib/api/types";

export default function DocumentsPage() {
  const { data, error, loading, reload } = useAsync(listDocuments);
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const items = data?.items ?? [];

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteDocument(pendingDelete.id);
      setPendingDelete(null);
      reload();
    } catch (err) {
      setDeleteError(isAppError(err) ? err.userMessage : "删除失败，请稍后重试");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="display text-ink">资料库</h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          资料是写章时的检索来源。上传后系统会自动解析、切段；没有文字的扫描件不会被检索到。
        </p>
      </div>

      <Card>
        <CardTitle>上传资料</CardTitle>
        <UploadPanel onUploaded={() => reload()} />
      </Card>

      <Card>
        <CardTitle
          action={
            <Button variant="outlined" onClick={reload} disabled={loading}>
              刷新
            </Button>
          }
        >
          资料列表{data ? `（${items.length} 份）` : ""}
        </CardTitle>

        {loading ? <LoadingBlock label="正在读取资料列表…" /> : null}

        {!loading && error ? (
          <StateBlock
            tone="error"
            title={error.userMessage}
            description="确认后端已启动（端口 8010）后重试。"
            action={<Button onClick={reload}>重新加载</Button>}
          />
        ) : null}

        {!loading && !error && items.length === 0 ? (
          <StateBlock
            title="还没有资料"
            description="先把项目的立项批复、报价单、规划文件等传上来，写章时才有东西可检索。"
          />
        ) : null}

        {!loading && !error && items.length > 0 ? (
          <DocumentList items={items} onDelete={(item) => setPendingDelete(item)} />
        ) : null}
      </Card>

      {pendingDelete ? (
        <div
          className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-title"
        >
          <div className="w-full max-w-md rounded-card border border-hairline bg-surface p-6">
            <h2 id="delete-title" className="text-[16px] font-semibold text-ink">
              删除这份资料？
            </h2>
            <p className="mt-2 text-[13px] leading-6 text-ink-muted">
              「{pendingDelete.filename}」会被删除，已写好的正文不会受影响，但之后再写章就检索不到它。
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
