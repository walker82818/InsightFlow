"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { checkHealth } from "@/lib/api";

export default function HomePage() {
  const [status, setStatus] = useState<string>("检测中…");

  useEffect(() => {
    checkHealth()
      .then(() => setStatus("后端已连接"))
      .catch(() => setStatus("后端未连接"));
  }, []);

  return (
    <div className="space-y-6">
      <section className="rounded-xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
        <h1 className="text-2xl font-bold text-slate-900">
          InsightFlow · AI 数据分析与可视化 Agent
        </h1>
        <p className="mt-2 text-slate-600">
          上传数据集，自动识别 Schema 与字段统计，后续由 Agent 完成分析与可视化。
        </p>
        <div className="mt-4 flex items-center gap-3">
          <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
            {status}
          </span>
          <Link
            href="/datasets"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            前往数据集
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {[
          ["上传 & 校验", "CSV / Excel / JSON，自动校验扩展名与大小"],
          ["Schema 识别", "自动推断 string / integer / float / date / category"],
          ["字段统计", "缺失值、重复行、分布与预览一目了然"],
        ].map(([t, d]) => (
          <div
            key={t}
            className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200"
          >
            <h3 className="font-semibold text-slate-900">{t}</h3>
            <p className="mt-1 text-sm text-slate-600">{d}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
