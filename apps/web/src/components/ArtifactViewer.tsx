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
  /**
   * mount 前的错峰延迟（毫秒）。「同页多 iframe」场景（artifacts-demo / Agent 多图表）
   * 下串行错开 esbuild-wasm 初始化，避免并发 fetch 11MB wasm + 编译导致部分 iframe
   * 卡死（宿主浏览器资源/连接数瓶颈）。生产页面（AnalysisChat）默认 0。
   */
  mountDelay?: number;
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
  mountDelay = 0,
}: ArtifactViewerProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const specRef = useRef(spec);
  specRef.current = spec;

  // onError 只存 ref，避免父组件 inline 回调导致 effect 反复触发
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const [height, setHeight] = useState(minHeight);

  // runtime 是否「活着」：收到过它的 ready/resize 消息即视为就绪。
  // 不能依赖 iframe load 事件——Next hydration 后 load/初始 ready 都可能已经错过。
  const runtimeReadyRef = useRef(false);

  // 接收 runtime 的 ready/resize/error 消息（校验 event.source）
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const win = iframeRef.current?.contentWindow;
      if (!win || e.source !== win) return;
      const parsed = FrameToParentSchema.safeParse(e.data);
      if (!parsed.success) return;
      const msg = parsed.data;
      if (msg.type === "ready" || msg.type === "resize") {
        runtimeReadyRef.current = true;
        setHeight(Math.max(msg.height, minHeight));
      } else if (msg.type === "error") {
        onErrorRef.current?.(msg.error);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [minHeight]);

  // 挂载驱动：mountDelay 错峰后，由 interval 反复尝试，
  // 直到「收到过 runtime 消息」或「重试超时（强制，runtime IIFE 同步执行后 listener 必在）」
  // 再真正 post mount（幂等：每次 doMount 只发一次，后续轮询短路）。
  useEffect(() => {
    const code = spec.code;
    if (!code) return;

    let stopped = false;
    let mounted = false;
    let attempts = 0;

    const doMount = () => {
      if (stopped || mounted) return;
      const win = iframeRef.current?.contentWindow;
      if (!win) return;

      const illegal = extractImports(code).filter((m) => !WHITELIST.has(m));
      if (illegal.length > 0) {
        onErrorRef.current?.({
          message: `生成代码包含白名单外 import: ${illegal.join(", ")}`,
        });
        mounted = true;
        return;
      }

      const { data, theme } = specRef.current;
      win.postMessage({ type: "mount", code, data, theme }, "*");
      mounted = true;
    };

    const timer = setTimeout(() => {
      if (stopped) return;
      // mountDelay 到期：若 runtime 已就绪立即发；否则交给 interval 兜底
      if (runtimeReadyRef.current) doMount();
    }, mountDelay);

    const interval = setInterval(() => {
      if (stopped || mounted) return;
      attempts += 1;
      // runtime 就绪 或 重试超时（约 5s）→ 强制挂载
      if (runtimeReadyRef.current || attempts > 8) doMount();
    }, 600);

    return () => {
      stopped = true;
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, [spec.code, mountDelay]);

  // 卸载时通知 runtime 清理
  useEffect(() => {
    return () => {
      iframeRef.current?.contentWindow?.postMessage({ type: "unmount" }, "*");
    };
  }, []);

  return (
    <div className={className} style={{ height }}>
      <iframe
        ref={iframeRef}
        src={RUNTIME_URL}
        sandbox="allow-scripts"
        title={spec.title || "artifact"}
        className="block h-full w-full border-0"
      />
    </div>
  );
}
