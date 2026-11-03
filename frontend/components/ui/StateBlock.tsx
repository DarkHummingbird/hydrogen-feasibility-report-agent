import type { ReactNode } from "react";

export function StateBlock({
  title,
  description,
  action,
  tone = "neutral",
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "error";
}) {
  return (
    <div className="rounded-card border border-dashed border-hairline bg-surface px-6 py-12 text-center">
      <p className={`text-[15px] font-medium ${tone === "error" ? "text-vermillion" : "text-ink"}`}>
        {title}
      </p>
      {description ? (
        <div className="mt-1.5 text-[13px] leading-6 text-ink-muted">{description}</div>
      ) : null}
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function LoadingBlock({ label = "正在加载…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 py-12 text-[13px] text-ink-muted"
    >
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-hairline border-t-primary" />
      {label}
    </div>
  );
}
