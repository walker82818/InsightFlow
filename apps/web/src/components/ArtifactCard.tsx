"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ArtifactSpec } from "@insightflow/artifact-schema";
import ArtifactViewer, {
  type ArtifactError,
} from "@/components/ArtifactViewer";
import { repairArtifact, shotArtifact } from "@/lib/api";

/** 设计 §4：错误自愈上限（iframe 编译/渲染失败 → LLM 修复重试轮数）。 */
const MAX_REPAIR_ATTEMPTS = 3;

/**
 * Agent2UI artifact 卡片：渲染 ArtifactViewer，并驱动「渲染失败 → LLM 修复 → 重挂载」自愈循环。
 *
 * - ``analysisId`` 为空时不做自愈（如历史详情页），失败直接展示错误卡片。
 * - 自愈失败耗尽后展示错误 + 「重新生成」按钮（回到初始 spec 重试）。
 */
export default function ArtifactCard({
  spec,
  analysisId,
}: {
  spec: ArtifactSpec;
  analysisId?: string | null;
}) {
  const [current, setCurrent] = useState(spec);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<ArtifactError | null>(null);
  const [repairing, setRepairing] = useState(false);
  const [shooting, setShooting] = useState(false);
  const repairingRef = useRef(false);

  /** 复用后端 Playwright 截图服务，把当前 artifact 保存为 PNG。 */
  const downloadImage = useCallback(async () => {
    if (shooting) return;
    setShooting(true);
    try {
      const blob = await shotArtifact(current);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(current.title || "artifact").replace(/[\\/:*?"<>|]/g, "_")}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError({ message: `保存图片失败：${(e as Error).message}` });
    } finally {
      setShooting(false);
    }
  }, [current, shooting]);

  // 父级下发新 spec（新一轮分析）时整体重置
  useEffect(() => {
    setCurrent(spec);
    setAttempt(0);
    setError(null);
  }, [spec]);

  const handleError = useCallback(
    async (err: ArtifactError) => {
      if (repairingRef.current) return; // 防并发重入
      if (!analysisId) {
        setError(err);
        return;
      }
      repairingRef.current = true;
      try {
        if (attempt < MAX_REPAIR_ATTEMPTS) {
          setRepairing(true);
          const fixed = await repairArtifact(
            analysisId,
            current,
            err,
            attempt + 1,
          );
          setAttempt((a) => a + 1);
          setError(null);
          setCurrent(fixed); // code 变化 → ArtifactViewer 重新 mount
        } else {
          setError(err);
        }
      } catch (e) {
        setError({
          message: `AI 修复失败：${(e as Error).message}`,
        });
      } finally {
        setRepairing(false);
        repairingRef.current = false;
      }
    },
    [analysisId, attempt, current],
  );

  const reset = useCallback(() => {
    setAttempt(0);
    setError(null);
    setCurrent(spec); // 用初始 spec 重新尝试
  }, [spec]);

  return (
    <div className="fade-up">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">
          {current.title || "AI 可视化"}
        </span>
        <span className="flex items-center gap-2">
          {!error && !repairing && (
            <button
              onClick={downloadImage}
              disabled={shooting}
              className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[11px] text-muted transition hover:border-line-strong hover:text-ink disabled:cursor-wait disabled:opacity-60"
              title="保存为图片（后端 Playwright 渲染）"
            >
              {shooting ? "截图中…" : "保存为图片"}
            </button>
          )}
          {repairing && (
            <span className="flex items-center gap-1 text-xs text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber" />
              AI 修复中…
            </span>
          )}
          {attempt > 0 && !error && (
            <span className="tag !py-0.5 !text-[11px]">
              已自动修复 {attempt}/{MAX_REPAIR_ATTEMPTS}
            </span>
          )}
        </span>
      </div>
      {error ? (
        <div className="rounded-xl border border-danger-soft bg-danger-soft/40 p-4">
          <div className="text-sm font-semibold text-danger">渲染失败</div>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">
            {error.message}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {attempt > 0 && (
              <span className="text-xs text-muted">
                已尝试修复 {attempt} 次未成功
              </span>
            )}
            <button className="btn btn-primary" onClick={reset}>
              重新生成
            </button>
          </div>
        </div>
      ) : (
        <ArtifactViewer spec={current} onError={handleError} minHeight={220} />
      )}
    </div>
  );
}
