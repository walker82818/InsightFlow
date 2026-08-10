"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getDataset } from "@/lib/api";
import type { DatasetColumn, DatasetDetail } from "@/types/dataset";

const TYPE_BADGE: Record<string, string> = {
  string: "bg-slate-100 text-slate-700",
  integer: "bg-emerald-100 text-emerald-700",
  float: "bg-sky-100 text-sky-700",
  date: "bg-violet-100 text-violet-700",
  category: "bg-amber-100 text-amber-700",
  boolean: "bg-pink-100 text-pink-700",
};

function StatLine({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="flex justify-between gap-2 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-slate-800">{String(value)}</span>
    </div>
  );
}

function ColumnStats({ col }: { col: DatasetColumn }) {
  const s = col.stats;
  return (
    <div className="space-y-1">
      <StatLine label="计数" value={s.count} />
      <StatLine label="缺失" value={s.missing !== undefined ? `${s.missing} (${(s.missing_ratio as number) * 100}%)` : undefined} />
      <StatLine label="去重" value={s.distinct} />
      {col.type === "integer" || col.type === "float" ? (
        <>
          <StatLine label="最小" value={s.min} />
          <StatLine label="最大" value={s.max} />
          <StatLine label="均值" value={s.mean} />
          <StatLine label="中位" value={s.median} />
          <StatLine label="标准差" value={s.std} />
        </>
      ) : null}
      {col.type === "date" ? (
        <>
          <StatLine label="最早" value={s.min} />
          <StatLine label="最晚" value={s.max} />
        </>
      ) : null}
      {col.type === "string" ? <StatLine label="平均长度" value={s.avg_length} /> : null}
      {col.type === "category" || col.type === "boolean" ? (
        <div className="pt-1">
          <p className="text-xs text-slate-500">Top 值</p>
          <ul className="mt-1 space-y-0.5">
            {((s.top_values as { value: unknown; count: number }[]) ?? []).map(
              (t) => (
                <li key={String(t.value)} className="flex justify-between text-xs">
                  <span className="text-slate-700">{String(t.value)}</span>
                  <span className="font-mono text-slate-500">{t.count}</span>
                </li>
              ),
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export default function DatasetDetailPage() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const [data, setData] = useState<DatasetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDataset(id)
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-sm text-slate-500">加载中…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!data) return <p className="text-sm text-slate-500">未找到数据集</p>;

  const previewCols = data.preview[0] ? Object.keys(data.preview[0]) : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/datasets" className="text-sm text-indigo-600 hover:underline">
            ← 返回数据集
          </Link>
          <h1 className="mt-1 text-xl font-bold text-slate-900">{data.name}</h1>
          <p className="text-xs text-slate-500">
            {data.file_name} · {data.file_type.toUpperCase()}
          </p>
        </div>
      </div>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          ["行数", data.profile.row_count],
          ["列数", data.profile.column_count],
          ["重复行", data.profile.duplicate_rows],
          ["缺失值", `${data.profile.total_missing} (${(data.profile.missing_ratio * 100).toFixed(1)}%)`],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200"
          >
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </section>

      <section className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <h2 className="border-b border-slate-100 p-4 text-sm font-semibold text-slate-700">
          Schema 与字段统计
        </h2>
        <div className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-3">
          {data.columns.map((c) => (
            <div key={c.name} className="bg-white p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-900">{c.name}</span>
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${TYPE_BADGE[c.type] ?? "bg-slate-100 text-slate-700"}`}
                >
                  {c.type}
                </span>
              </div>
              <div className="mt-2">
                <ColumnStats col={c} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <h2 className="border-b border-slate-100 p-4 text-sm font-semibold text-slate-700">
          数据预览（前 {data.preview.length} 行）
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
              <tr>
                {previewCols.map((col) => (
                  <th key={col} className="p-3 font-medium">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.preview.map((row, i) => (
                <tr key={i} className="border-b border-slate-100 last:border-0">
                  {previewCols.map((col) => (
                    <td key={col} className="p-3 font-mono text-xs text-slate-700">
                      {row[col] === null || row[col] === undefined
                        ? "—"
                        : String(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
