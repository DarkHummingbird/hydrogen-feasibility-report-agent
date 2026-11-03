import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outlined" | "text";

/** DESIGN.md：全站只有一个填充按钮（#0075de），其余用 sky tint 幽灵按钮或纯文字按钮。 */
const styles: Record<Variant, string> = {
  primary:
    "bg-primary text-white border border-primary hover:bg-primary-hover disabled:bg-primary/40 disabled:border-primary/40",
  ghost:
    "bg-sky-tint text-primary border border-transparent hover:bg-[#d7ebfd] disabled:text-primary/40",
  outlined:
    "bg-transparent text-ink border border-hairline hover:border-ink/40 disabled:text-ink/40",
  text: "bg-transparent text-ink/90 border border-transparent hover:bg-black/5 disabled:text-ink/40",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <button
      type="button"
      {...rest}
      className={`transition-ui inline-flex min-h-9 items-center justify-center gap-1.5 rounded-control px-3.5 text-[14px] font-medium disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}
