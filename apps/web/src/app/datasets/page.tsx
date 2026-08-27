"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-slate-900">数据集</h1>

      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-sm font-semibold text-slate-700">上传新数据集</h2>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-slate-500">
            文件 (CSV / XLSX / JSON)
            <input
              type="file"
              accept=".csv,.xlsx,.xls,.json"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 block text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-indigo-600 hover:file:bg-indigo-100"
            />
          </label>
          <label className="flex flex-col text-xs text-slate-500">
            名称（可选）
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="默认使用文件名"
              className="mt-1 w-48 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800"
            />
          </label>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {uploading ? "上传中…" : "上传"}
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </div>

      <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        {selected.size > 0 && (
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-indigo-50/60 px-4 py-3">
            <span className="text-sm text-slate-700">
              已选 <span className="font-semibold text-indigo-600">{selected.size}</span> 张表
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSelected(new Set())}
                className="text-sm text-slate-500 hover:text-slate-800"
              >
                取消选择
              </button>
              <button
                onClick={startAnalysis}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                开始分析（{selected.size}）
              </button>
            </div>
          </div>
        )}
        {loading ? (
          <p className="p-6 text-sm text-slate-500">加载中…</p>
        ) : datasets.length === 0 ? (
          <p className="p-6 text-sm text-slate-500">还没有数据集，先上传一个吧。</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-slate-500">
              <tr>
                <th className="w-10 p-4">
                  <input
                    type="checkbox"
                    checked={selected.size === datasets.length}
                    onChange={toggleAll}
                    aria-label="全选"
                    className="h-4 w-4 accent-indigo-600"
                  />
                </th>
                <th className="p-4">名称</th>
                <th className="p-4">类型</th>
                <th className="p-4">行 × 列</th>
                <th className="p-4">大小</th>
                <th className="p-4">字段</th>
                <th className="p-4"></th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr
                  key={d.id}
                  className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                    selected.has(d.id) ? "bg-indigo-50/40" : ""
                  }`}
                >
                  <td className="p-4">
                    <input
                      type="checkbox"
                      checked={selected.has(d.id)}
                      onChange={() => toggle(d.id)}
                      aria-label={`选择 ${d.name}`}
                      className="h-4 w-4 accent-indigo-600"
                    />
                  </td>
                  <td className="p-4 font-medium text-slate-900">{d.name}</td>
                  <td className="p-4 uppercase text-slate-500">{d.file_type}</td>
                  <td className="p-4 text-slate-600">
                    {d.row_count} × {d.column_count}
                  </td>
                  <td className="p-4 text-slate-600">{formatSize(d.file_size)}</td>
                  <td className="p-4">
                    <div className="flex flex-wrap gap-1">
                      {d.columns.map((c) => (
                        <span
                          key={c.name}
                          className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                          title={`${c.type}`}
                        >
                          {c.name}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="p-4 text-right">
                    <Link
                      href={`/datasets/${d.id}`}
                      className="mr-3 text-indigo-600 hover:underline"
                    >
                      查看
                    </Link>
                    <button
                      onClick={() => handleDelete(d.id)}
                      className="text-red-600 hover:underline"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
