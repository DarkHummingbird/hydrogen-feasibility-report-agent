import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "可研报告生成Agent",
  description: "氢能项目可行性研究报告生成：上传资料、生成大纲、一键写全文、导出 Word",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        {/* DESIGN.md：固定顶栏 64px，发丝线分隔，不用重阴影 */}
        <header className="sticky top-0 z-10 border-b border-hairline bg-canvas/95 backdrop-blur">
          <div className="page-shell flex h-16 items-center gap-4 sm:gap-8">
            <Link
              href="/"
              className="shrink-0 whitespace-nowrap text-[15px] font-semibold tracking-[-0.2px] text-ink"
            >
              可研报告生成Agent
            </Link>
            <nav className="flex shrink-0 items-center gap-0.5 text-[14px] sm:gap-1" aria-label="主导航">
              <Link
                href="/"
                className="transition-ui rounded-control whitespace-nowrap px-2 py-1.5 text-ink/54 hover:bg-black/5 hover:text-ink sm:px-3"
              >
                报告
              </Link>
              <Link
                href="/documents"
                className="transition-ui rounded-control whitespace-nowrap px-2 py-1.5 text-ink/54 hover:bg-black/5 hover:text-ink sm:px-3"
              >
                资料库
              </Link>
            </nav>
            <span className="ml-auto hidden shrink-0 whitespace-nowrap text-[12px] text-ink-muted sm:block">
              氢能可研报告 · 本地版
            </span>
          </div>
        </header>
        <main className="page-shell py-8">{children}</main>
      </body>
    </html>
  );
}
