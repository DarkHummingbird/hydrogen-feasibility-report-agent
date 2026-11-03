/** 药丸标签（DESIGN.md Pill Tag）：9999px 圆角，颜色只从强调色系里取。 */
const toneStyles = {
  neutral: "bg-black/5 text-ink-muted",
  info: "bg-sky-tint text-primary",
  wait: "bg-marigold-tint text-saffron-ink",
  ok: "bg-[#e8f2e9] text-[#1c6b34]",
  error: "bg-danger-tint text-vermillion",
} as const;

export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: keyof typeof toneStyles;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-3 py-1 text-[12px] leading-5 font-medium ${toneStyles[tone]}`}
    >
      {children}
    </span>
  );
}
