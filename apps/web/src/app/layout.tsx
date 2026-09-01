import type { Metadata } from "next";
import "highlight.js/styles/github.css";
import "./globals.css";
import AuthNav from "@/components/AuthNav";

export const metadata: Metadata = {
  title: "InsightFlow — AI 数据分析与可视化",
  description:
    "上传数据，用自然语言提问，InsightFlow 自动完成分析、可视化与可解释报告。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Inter:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-40 border-b border-line bg-paper/80 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
            <a href="/" className="group flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-white shadow-sm transition-transform duration-300 group-hover:rotate-[8deg]">
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 17l5-6 4 3 5-8 4 5" />
                </svg>
              </span>
              <span className="font-display text-lg font-bold tracking-tight text-ink">
                InsightFlow
              </span>
            </a>
            <nav className="flex items-center gap-1 text-sm">
              <a
                href="/"
                className="btn-quiet rounded-lg px-3 py-2 font-medium"
              >
                工作台
              </a>
              <a
                href="/datasets"
                className="btn-quiet rounded-lg px-3 py-2 font-medium"
              >
                数据集
              </a>
              <span className="ml-1 hidden items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-muted sm:inline-flex">
                <span className="h-2 w-2 rounded-full bg-pine" />
                本地服务已连接
              </span>
              <AuthNav />
            </nav>
          </div>
        </header>
        {/* 宽度由各页面自管：普通页用 max-w-6xl 容器，对话工作台可全宽 */}
        <main className="w-full px-5 pb-24 pt-8">{children}</main>
        <footer className="border-t border-line bg-paper">
          <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-5 py-6 text-xs text-faint sm:flex-row">
            <span>InsightFlow · 让数据分析像对话一样自然</span>
            <span>由 AI 大模型驱动 · 支持私有化部署</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
