"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  deleteDataset,
  listDatasets,
  uploadDataset,
} from "@/lib/api";
import type { DatasetSummary } from "@/types/dataset";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  async function refresh() {
    setLoading(true);
    try {
      setDatasets(await listDatasets());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDataset(file, name || undefined);
      setFile(null);
      setName("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确认删除该数据集？")) return;
    try {
      await deleteDataset(id);
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === datasets.length) setSelected(new Set());
    else setSelected(new Set(datasets.map((d) => d.id)));
  }

  function startAnalysis() {
    if (selected.size === 0) return;
    const ids = datasets
      .filter((d) => selected.has(d.id))
      .map((d) => d.id);
    router.push(`/datasets/${ids[0]}?ids=${ids.join(",")}`);
  }

  const allChecked = datasets.length > 0 && selected.size === datasets.length;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      {/* Page header */}
      <header className="fade-up flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow">数据管理</div>
          <h1 className="mt-1 font-display text-2xl font-bold text-ink">
            数据集
          </h1>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
            上传、管理你的数据源。勾选多张表后，可一次性进入对话式分析工作台。
          </p>
        </div>
      </header>

      {/* Upload */}
      <section className="card p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-base font-semibold text-ink">
            上传新数据集
          </h2>
          <span className="tag">CSV / XLSX / JSON</span>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="group inline-flex h-11 items-center gap-2 rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 text-sm font-medium text-muted transition hover:border-accent hover:text-ink"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
            </svg>
            {file ? (
              <span className="max-w-[240px] truncate text-ink-soft">
                {file.name}
              </span>
            ) : (
              "选择文件"
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls,.json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="hidden"
          />

          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted">
            名称（可选）
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="默认使用文件名"
              className="input h-11 w-56"
            />
          </label>

          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="btn btn-primary h-11"
          >
            {uploading ? "上传中…" : "上传"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-danger/20 bg-danger/5 px-3 py-2.5 text-sm text-danger">
            {error}
          </div>
        )}
      </section>

      {/* Dataset list */}
      <section className="card overflow-hidden">
        {selected.size > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-accent-soft/50 px-5 py-3">
            <span className="text-sm text-ink-soft">
              已选{" "}
              <span className="font-semibold text-accent-strong">
                {selected.size}
              </span>{" "}
              张表
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelected(new Set())}
                className="btn-quiet rounded-lg px-3 py-2 text-sm font-medium"
              >
                取消选择
              </button>
              <button onClick={startAnalysis} className="btn btn-primary">
                开始分析（{selected.size}）
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-32">
                <div className="skeleton h-5 w-1/2" />
                <div className="skeleton mt-3 h-3 w-3/4" />
                <div className="skeleton mt-2 h-3 w-2/3" />
              </div>
            ))}
          </div>
        ) : datasets.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v18h18M7 14l3-3 3 3 5-6" />
              </svg>
            </div>
            <div className="font-display text-lg font-semibold text-ink">
              还没有数据集
            </div>
            <p className="max-w-sm text-sm text-muted">
              上传一个 CSV / XLSX / JSON 文件，开始你的第一次分析。
            </p>
            <button
              className="btn btn-primary"
              onClick={() => fileRef.current?.click()}
            >
              导入数据集
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-faint">
                  <th className="w-12 px-5 py-3.5">
                    <input
                      type="checkbox"
                      checked={allChecked}
                      onChange={toggleAll}
                      aria-label="全选"
                      className="h-4 w-4 cursor-pointer accent-accent"
                    />
                  </th>
                  <th className="px-4 py-3.5 font-semibold">名称</th>
                  <th className="px-4 py-3.5 font-semibold">类型</th>
                  <th className="px-4 py-3.5 font-semibold">行 × 列</th>
                  <th className="px-4 py-3.5 font-semibold">大小</th>
                  <th className="px-4 py-3.5 font-semibold">字段</th>
                  <th className="px-4 py-3.5 text-right font-semibold">操作</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((d) => {
                  const isSelected = selected.has(d.id);
                  return (
                    <tr
                      key={d.id}
                      onClick={() => router.push(`/datasets/${d.id}`)}
                      className={`group cursor-pointer border-b border-line transition last:border-0 ${
                        isSelected
                          ? "bg-accent-soft/40"
                          : "hover:bg-surface-2"
                      }`}
                    >
                      <td
                        className="px-5 py-3.5"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggle(d.id)}
                          aria-label={`选择 ${d.name}`}
                          className="h-4 w-4 cursor-pointer accent-accent"
                        />
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-ink">
                            {d.name}
                          </span>
                          {d.source_type === "db" && (
                            <span className="tag tag-pine !py-0.5 !text-[11px]">
                              数据库
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3.5 uppercase text-muted">
                        {d.file_type}
                      </td>
                      <td className="px-4 py-3.5 text-ink-soft">
                        {d.row_count} × {d.column_count}
                      </td>
                      <td className="px-4 py-3.5 text-muted">
                        {formatSize(d.file_size)}
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex max-w-[260px] flex-wrap gap-1">
                          {d.columns.map((c) => (
                            <span
                              key={c.name}
                              className="tag !py-0.5 !text-[11px]"
                              title={`${c.type}`}
                            >
                              {c.name}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td
                        className="px-4 py-3.5 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => handleDelete(d.id)}
                          className="font-medium text-danger transition hover:underline"
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
