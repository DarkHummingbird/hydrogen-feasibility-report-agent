import { Suspense } from "react";
import { LoadingBlock } from "@/components/ui/StateBlock";
import { OutlineView } from "@/features/outline/components/OutlineView";

/** 这个路由依赖 URL 里的报告 ID，构建期没有具体参数，标记为阻塞渲染即可（Next 16 提示的做法）。 */
export const instant = false;
export default async function OutlinePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={<LoadingBlock label="正在读取报告…" />}>
      <OutlineView reportId={id} />
    </Suspense>
  );
}
