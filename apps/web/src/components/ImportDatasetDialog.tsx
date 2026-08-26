"use client";

import { useState } from "react";

export default function ImportDatasetDialog({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (file: File, name: string) => Promise<unknown>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handle() {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(file, name);
      setFile(null);
      setName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold text-ink">
            导入数据集
          </h3>
          <button
            className="btn-quiet rounded-lg p-1.5"
            onClick={onClose}
            aria-label="关闭"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p className="mt-1 text-sm text-muted">
          上传后系统会自动解析字段类型、统计特征与缺失情况。
        </p>

        <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 py-8 text-center transition hover:border-accent">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
          </svg>
          <span className="text-sm font-medium text-ink-soft">
            {file ? file.name : "点击选择文件"}
          </span>
          <span className="text-xs text-faint">CSV / Parquet / XLSX / JSON</span>
          <input
            type="file"
            accept=".csv,.parquet,.xlsx,.xls,.json"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <input
          className="input mt-3"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="数据集名称（可选，默认用文件名）"
        />

        {error && (
          <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            取消
          </button>
          <button
            className="btn btn-primary"
            onClick={handle}
            disabled={!file || submitting}
          >
            {submitting ? "导入中…" : "导入"}
          </button>
        </div>
      </div>
    </div>
  );
}
