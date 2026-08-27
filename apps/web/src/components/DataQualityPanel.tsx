"use client";

import { useEffect, useState } from "react";
import { getDatasetProfile2, errMsg } from "@/lib/api";
import type { DatasetProfile2 } from "@/lib/api";

const SEV_LABEL: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const ROLE_LABEL: Record<string, string> = {
  id: "ID",
  time: "时间",
  dimension: "维度",
  metric: "指标",
  numeric_dimension: "数值维度",
  text: "文本",
};

export default function DataQualityPanel({ datasetId }: { datasetId: string }) {
  const [profile, setProfile] = useState<DatasetProfile2 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const p = await getDatasetProfile2(datasetId);
        if (!cancelled) setProfile(p);
      } catch (e) {
        if (!cancelled) {
          setError(errMsg(e));
          setProfile(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (loading) {
    return (
      <div className="card p-4">
        <div className="skeleton h-4 w-1/3" />
        <div className="skeleton mt-3 h-20 w-full" />
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="card p-4">
        <div className="eyebrow">数据质量</div>
        <div className="mt-2 text-xs text-muted">
          {error ?? "暂无 2.0 画像，请重新上传数据集。"}
        </div>
      </div>
    );
  }

  const score = profile.quality_score;
  const scoreColor =
    score >= 90 ? "text-pine" : score >= 75 ? "text-amber" : "text-danger";

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="eyebrow">数据质量</div>
        <span className={`font-display text-xl font-bold ${scoreColor}`}>
          {score}
          <span className="text-xs text-faint">/100</span>
        </span>
      </div>

      {/* Field roles */}
      <div className="mt-3">
        <div className="mb-1.5 text-xs text-muted">字段角色</div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(profile.schema.roles).map(([col, role]) => (
            <span
              key={col}
              className="tag !py-0.5 !text-[11px]"
              title={`${col} · ${ROLE_LABEL[role] ?? role}`}
            >
              {col}
            </span>
          ))}
        </div>
      </div>

      {/* Issues */}
      <div className="mt-3">
        <div className="mb-1.5 text-xs text-muted">
          问题 · {profile.issues.length}
        </div>
        {profile.issues.length === 0 ? (
          <div className="rounded-xl bg-pine-soft px-3 py-2 text-xs text-pine">
            未发现明显数据质量问题
          </div>
        ) : (
          <div className="max-h-52 space-y-1.5 overflow-auto pr-1">
            {profile.issues.map((iss, i) => (
              <div
                key={i}
                className="rounded-xl border border-line bg-surface px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-semibold text-ink">
                    {iss.column}
                  </span>
                  <span
                    className={`tag !py-0 !text-[10px] ${
                      iss.severity === "high"
                        ? "!text-danger"
                        : iss.severity === "medium"
                          ? "!text-amber"
                          : "!text-muted"
                    }`}
                  >
                    {SEV_LABEL[iss.severity] ?? iss.severity}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted">{iss.message}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Anomalies */}
      {profile.anomalies.length > 0 && (
        <div className="mt-3">
          <div className="mb-1.5 text-xs text-muted">
            异常 · {profile.anomalies.length}
          </div>
          <div className="max-h-40 space-y-1.5 overflow-auto pr-1">
            {profile.anomalies.map((a, i) => (
              <div
                key={i}
                className="rounded-xl bg-amber-soft px-3 py-2 text-xs text-amber"
              >
                {a.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
