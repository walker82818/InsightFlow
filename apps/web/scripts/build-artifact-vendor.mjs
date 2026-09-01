// Agent2UI：把 iframe runtime 依赖的第三方库 bundle 成本地 ESM，供 importmap 使用。
// 目的：sandbox（opaque origin）下无法跨源动态 import 模块（CORS 限制），
//       且 CDN 在部分网络不可达 → 全部本地化，runtime 完全离网运行。
//
// 运行方式（在 apps/web 目录下）：
//   node scripts/build-artifact-vendor.mjs
//
// React 全家桶合并为单文件 vendor/react.js：
//   - react / react/jsx-runtime / react-dom/client 三个 importmap 键都指向它，
//     避免 CJS entry 打包 ESM 时 external 依赖残留 `require("react")`（浏览器不支持），
//     也避免 React 双实例导致 hooks 报错。
import { build } from "esbuild";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";

const outdir = path.join(process.cwd(), "public", "_artifacts", "vendor");
await mkdir(outdir, { recursive: true });

const common = {
  bundle: true,
  format: "esm",
  target: "es2020",
  platform: "browser",
  logLevel: "info",
  // React 源码里 process.env.NODE_ENV 的 branch：生产构建必须 define，否则浏览器 import 报 process is not defined
  define: { "process.env.NODE_ENV": '"production"' },
};

// ---- react 全家桶（react + jsx-runtime + react-dom/client） ----
const reactEntry = `
import React from "react";
import { jsx, jsxs, Fragment } from "react/jsx-runtime";
import { createRoot, hydrateRoot } from "react-dom/client";

export default React;
export const useState = React.useState;
export const useEffect = React.useEffect;
export const useRef = React.useRef;
export const useMemo = React.useMemo;
export const useCallback = React.useCallback;
export const useContext = React.useContext;
export const useReducer = React.useReducer;
export const useLayoutEffect = React.useLayoutEffect;
export const useTransition = React.useTransition;
export const useDeferredValue = React.useDeferredValue;
export const useId = React.useId;
export const createContext = React.createContext;
export const createElement = React.createElement;
export const StrictMode = React.StrictMode;
export const memo = React.memo;
export const forwardRef = React.forwardRef;
export const lazy = React.lazy;
export const Suspense = React.Suspense;
export const startTransition = React.startTransition;
export { jsx, jsxs, Fragment };
export { createRoot, hydrateRoot };
`;
await build({
  ...common,
  stdin: {
    contents: reactEntry,
    sourcefile: "vendor-react-entry.js",
    resolveDir: process.cwd(),
  },
  outfile: path.join(outdir, "react.js"),
});

// ---- echarts：自包含（zrender 已内联） ----
await build({
  ...common,
  entryPoints: ["echarts"],
  outfile: path.join(outdir, "echarts.js"),
});

// 旧的独立 jsx-runtime / react-dom 产物已并入 react.js，清理避免误导
await rm(path.join(outdir, "react-jsx-runtime.js"), { force: true });
await rm(path.join(outdir, "react-dom-client.js"), { force: true });

console.log("artifact vendor bundle done →", outdir);
