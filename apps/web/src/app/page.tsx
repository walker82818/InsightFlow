"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listDatasets, uploadDataset } from "@/lib/api";
import type { DatasetSummary } from "@/types/dataset";
import DatasetCard from "@/components/DatasetCard";
import ImportDatasetDialog from "@/components/ImportDatasetDialog";
import ConnectDatabaseDialog from "@/components/ConnectDatabaseDialog";

export default function HomePage() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImportOpen] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await listDatasets();
        if (!cancelled) setDatasets(rows);
      } catch {
        /* 忽略 */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleImport(file: File, name: string) {
    const d = await uploadDataset(file, name);
    setDatasets((prev) => [d, ...prev]);
    setImportOpen(false);
    return d;
  }

  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="fade-up relative overflow-hidden rounded-[28px] border border-line bg-surface px-7 py-12 sm:px-12 sm:py-16">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent-soft blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-24 left-10 h-56 w-56 rounded-full bg-pine-soft blur-3xl opacity-70"
        />
        <div className="relative max-w-2xl">
          <span className="tag-accent mb-4 inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            数据分析 · 像聊天一样简单
          </span>
          <h1 className="font-display text-4xl font-bold leading-[1.08] tracking-tight text-ink sm:text-5xl">
            把数据交给对话，
            <br />
            把洞察交给自己。
          </h1>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-ink-soft">
            InsightFlow 用本地大模型理解你的自然语言提问，自动完成查询、分析与可视化，
            并生成一份可解释、可复核、可导出的分析报告。数据始终留在你的机器上。
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <button className="btn btn-primary" onClick={() => setImportOpen(true)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
              </svg>
              导入数据集
            </button>
            <button className="btn btn-ghost" onClick={() => setConnectOpen(true)}>
              连接数据库
            </button>
            <span className="text-sm text-muted">
              支持文件上传，或直接连接 PostgreSQL / MySQL / SQLite
            </span>
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            <span className="tag bg-surface-2 text-ink-soft">SQL + Python 双引擎</span>
            <span className="tag bg-surface-2 text-ink-soft">2D / 3D 可视化</span>
            <span className="tag bg-surface-2 text-ink-soft">可解释报告</span>
            <span className="tag bg-surface-2 text-ink-soft">数据不出域</span>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="grid gap-4 sm:grid-cols-3">
        {[
          {
            n: "01",
            t: "导入数据",
            d: "上传文件，系统会自动识别字段类型、统计分布与缺失情况。",
          },
          {
            n: "02",
            t: "对话式提问",
            d: "用大白话描述你想知道的，Agent 会规划、查询并画图。",
          },
          {
            n: "03",
            t: "获取报告",
            d: "一键生成带图表、证据与建议的分析报告，随时回看导出。",
          },
        ].map((s) => (
          <div key={s.n} className="tile fade-up p-5">
            <div className="font-display text-2xl font-bold text-accent">{s.n}</div>
            <div className="mt-2 font-display text-base font-semibold text-ink">
              {s.t}
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{s.d}</p>
          </div>
        ))}
      </section>

      {/* Datasets */}
      <section>
        <div className="mb-4 flex items-end justify-between">
          <div>
            <div className="eyebrow">你的工作台</div>
            <h2 className="mt-1 font-display text-2xl font-bold text-ink">数据集</h2>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-ghost" onClick={() => setConnectOpen(true)}>
              连接数据库
            </button>
            <button className="btn btn-primary" onClick={() => setImportOpen(true)}>
              导入数据集
            </button>
          </div>
        </div>

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="card h-36 p-5">
                <div className="skeleton h-5 w-1/2" />
                <div className="skeleton mt-3 h-3 w-3/4" />
                <div className="skeleton mt-2 h-3 w-2/3" />
              </div>
            ))}
          </div>
        ) : datasets.length === 0 ? (
          <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v18h18M7 14l3-3 3 3 5-6" />
              </svg>
            </div>
            <div className="font-display text-lg font-semibold text-ink">
              还没有数据集
            </div>
            <p className="max-w-sm text-sm text-muted">
              上传一个 CSV / Parquet 文件，开始你的第一次分析。
            </p>
            <button className="btn btn-primary" onClick={() => setImportOpen(true)}>
              导入数据集
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {datasets.map((d) => (
              <Link key={d.id} href={`/datasets/${d.id}`} className="fade-up">
                <DatasetCard dataset={d} />
              </Link>
            ))}
          </div>
        )}
      </section>

      <ImportDatasetDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onSubmit={handleImport}
      />

      {connectOpen && (
        <ConnectDatabaseDialog
          onClose={() => setConnectOpen(false)}
          onCreated={(d) => {
            setDatasets((prev) => [d, ...prev]);
            setConnectOpen(false);
          }}
        />
      )}
    </div>
  );
}
