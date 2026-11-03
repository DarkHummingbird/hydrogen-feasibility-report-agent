import { StatusBadge } from "@/components/ui/StatusBadge";
import type { DocumentItem } from "@/lib/api/types";

const STATUS: Record<string, { text: string; tone: "ok" | "wait" | "error" }> = {
  available: { text: "可用", tone: "ok" },
  no_text: { text: "无文字", tone: "wait" },
  failed: { text: "失败", tone: "error" },
};

function sizeText(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function statusOf(item: DocumentItem) {
  return STATUS[item.status] ?? { text: "未知状态", tone: "neutral" as const };
}

/** 桌面用表格；手机改成卡片列表（手册 16.2：表格优先改成卡片，避免整页横向滚动）。 */
export function DocumentList({
  items,
  onDelete,
}: {
  items: DocumentItem[];
  onDelete: (item: DocumentItem) => void;
}) {
  return (
    <>
      {/* 手机：卡片列表 */}
      <ul className="flex flex-col gap-3 md:hidden">
        {items.map((item) => {
          const status = statusOf(item);
          return (
            <li key={item.id} className="rounded-card border border-hairline p-3">
              <p className="break-all text-[13px] font-medium text-ink">{item.filename}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-ink-muted">
                <StatusBadge tone={status.tone}>{status.text}</StatusBadge>
                <span>{item.status === "available" ? `${item.segments_count} 段` : "—"}</span>
                <span>{sizeText(item.size_bytes)}</span>
                <button
                  type="button"
                  onClick={() => onDelete(item)}
                  className="transition-ui ml-auto rounded-small px-2 py-1 text-ink-muted hover:bg-danger-tint hover:text-vermillion"
                >
                  删除
                </button>
              </div>
              {item.error ? <p className="mt-1 text-[12px] text-ink-muted">{item.error}</p> : null}
            </li>
          );
        })}
      </ul>

      {/* 桌面：表格 */}
      <div className="hidden w-full max-w-full md:block">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-hairline text-left text-[12px] text-ink-muted">
              <th className="py-2.5 pr-3 font-medium">文件名</th>
              <th className="whitespace-nowrap py-2.5 pr-3 font-medium">状态</th>
              <th className="whitespace-nowrap py-2.5 pr-3 font-medium">切段</th>
              <th className="whitespace-nowrap py-2.5 pr-3 font-medium">大小</th>
              <th className="py-2.5 pr-3 font-medium">
                <span className="sr-only">操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const status = statusOf(item);
              return (
                <tr key={item.id} className="border-b border-hairline/70 last:border-b-0">
                  <td className="max-w-[360px] py-3 pr-3 text-ink">
                    <span className="block truncate" title={item.filename}>
                      {item.filename}
                    </span>
                    {item.error ? (
                      <span className="mt-0.5 block text-[12px] text-ink-muted">{item.error}</span>
                    ) : null}
                  </td>
                  <td className="py-3 pr-3">
                    <StatusBadge tone={status.tone}>{status.text}</StatusBadge>
                  </td>
                  <td className="whitespace-nowrap py-3 pr-3 text-ink-muted">
                    {item.status === "available" ? `${item.segments_count} 段` : "—"}
                  </td>
                  <td className="whitespace-nowrap py-3 pr-3 text-ink-muted">
                    {sizeText(item.size_bytes)}
                  </td>
                  <td className="py-3 pr-3 text-right">
                    <button
                      type="button"
                      onClick={() => onDelete(item)}
                      className="transition-ui rounded-small px-2 py-1 text-[12px] text-ink-muted hover:bg-danger-tint hover:text-vermillion"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
