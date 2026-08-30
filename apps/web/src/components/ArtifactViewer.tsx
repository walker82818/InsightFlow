"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  FrameToParentSchema,
  type ArtifactSpec,
} from "@insightflow/artifact-schema";

const RUNTIME_URL = "/_artifacts/runtime.html";

export interface ArtifactError {
  message: string;
  line?: number;
  column?: number;
}

interface ArtifactViewerProps {
  spec: ArtifactSpec;
  onError?: (error: ArtifactError) => void;
  minHeight?: number;
  className?: string;
}

// 提取生成代码里的 import 说明符（含副作用导入），用于前端白名单预检。
// runtime 侧 importmap 仍是最终兜底拦截。
const IMPORT_FROM_RE = /import\s+(?:type\s+)?[\s\S]*?from\s*["']([^"']+)["']/g;
const SIDE_EFFECT_RE = /import\s*["']([^"']+)["']/g;

function extractImports(code: string): string[] {
  const found: string[] = [];
  let m: RegExpExecArray | null;
  for (const re of [IMPORT_FROM_RE, SIDE_EFFECT_RE]) {
    re.lastIndex = 0;
    while ((m = re.exec(code))) {
      const spec = m[1];
      if (!found.includes(spec)) found.push(spec);
    }
  }
  return found;
}

const WHITELIST = new Set([
  "react",
  "react/jsx-runtime",
  "react-dom/client",
  "echarts",
  "three",
  "/_artifacts/insight-ui.js",
]);

export default function ArtifactViewer({
  spec,
  onError,
  minHeight = 120,
  className,
}: ArtifactViewerProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const specRef = useRef(spec);
  specRef.current = spec;

  // onError 只存 ref，避免父组件 inline 回调导致 effect 反复触发
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const [loaded, setLoaded] = useState(false);
  const [height, setHeight] = useState(minHeight);

  // 记录已成功挂载的 code，code 未变化时不重复 mount
  const mountedCodeRef = useRef<string | null>(null);

  const postMount = useCallback((code: string) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    const { data, theme } = specRef.current;
    win.postMessage({ type: "mount", code, data, theme }, "*");
  }, []);

  // 白名单预检 + 触发挂载（仅 code 变化时）
  useEffect(() => {
    const code = spec.code;
    if (!loaded || mountedCodeRef.current === code) return;

    const illegal = extractImports(code).filter((m) => !WHITELIST.has(m));
    if (illegal.length > 0) {
      onErrorRef.current?.({
        message: `生成代码包含白名单外 import: ${illegal.join(", ")}`,
      });
      return;
    }

    mountedCodeRef.current = code;
    postMount(code);
  }, [spec.code, loaded, postMount]);

  // 接收 runtime 的 ready/resize/error 消息（校验 event.source）
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const win = iframeRef.current?.contentWindow;
      if (!win || e.source !== win) return;
      const parsed = FrameToParentSchema.safeParse(e.data);
      if (!parsed.success) return;
      const msg = parsed.data;
      if (msg.type === "ready" || msg.type === "resize") {
        setHeight(Math.max(msg.height, minHeight));
      } else if (msg.type === "error") {
        onErrorRef.current?.(msg.error);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [minHeight]);

  // 卸载时通知 runtime 清理
  useEffect(() => {
    return () => {
      iframeRef.current?.contentWindow?.postMessage({ type: "unmount" }, "*");
    };
  }, []);

  const handleLoad = useCallback(() => {
    setLoaded(true);
    mountedCodeRef.current = null; // 允许首次/重新挂载
  }, []);

  return (
    <div className={className} style={{ height }}>
      <iframe
        ref={iframeRef}
        src={RUNTIME_URL}
        sandbox="allow-scripts"
        title={spec.title || "artifact"}
        onLoad={handleLoad}
        className="block h-full w-full border-0"
      />
    </div>
  );
}
