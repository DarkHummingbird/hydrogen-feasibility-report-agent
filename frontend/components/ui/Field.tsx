import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

export function Label({ htmlFor, children }: { htmlFor: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[14px] font-medium text-ink">
      {children}
    </label>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-[12px] leading-5 text-ink-muted">{children}</p>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-1.5 text-[12px] leading-5 text-vermillion">
      {children}
    </p>
  );
}

const base =
  "transition-ui w-full rounded-control border border-hairline bg-surface px-3 py-2 text-[14px] text-ink placeholder:text-ink-soft focus:border-primary focus:outline-none";

export function Input(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const { invalid, className = "", ...rest } = props;
  return <input {...rest} className={`${base} ${invalid ? "border-vermillion" : ""} ${className}`} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  const { invalid, className = "", ...rest } = props;
  return (
    <textarea {...rest} className={`${base} min-h-20 ${invalid ? "border-vermillion" : ""} ${className}`} />
  );
}
