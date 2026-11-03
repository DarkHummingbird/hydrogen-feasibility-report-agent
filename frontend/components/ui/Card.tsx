import type { ReactNode } from "react";

/** DESIGN.md：白色卡片置在暖纸底上，12px 圆角 + 发丝边框，不用阴影。 */
export function Card({
  children,
  className = "",
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return (
    <Tag className={`rounded-card border border-hairline bg-surface p-6 ${className}`}>{children}</Tag>
  );
}

export function CardTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="display text-[20px] font-semibold">{children}</h2>
      {action}
    </div>
  );
}
