// Agent2UI：把 iframe runtime 依赖的第三方库 bundle 成本地 ESM，供 importmap 使用。
// 目的：sandbox（opaque origin）下无法跨源动态 import 模块（CORS 限制），
//       且 CDN 在部分网络不可达 → 全部本地化，runtime 完全离网运行。
//
// 运行方式（在 apps/web 目录下）：
//   node scripts/build-artifact-vendor.mjs
import { build } from "esbuild";
import { mkdir } from "node:fs/promises";
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

// react 本体：自包含
await build({
  ...common,
  entryPoints: ["react"],
  outfile: path.join(outdir, "react.js"),
});

// react/jsx-runtime 与 react-dom/client：保持 import "react" 外部化，
// 复用 importmap 中同一份 react.js，避免 React 双实例导致 hooks 报错。
await build({
  ...common,
  entryPoints: ["react/jsx-runtime"],
  outfile: path.join(outdir, "react-jsx-runtime.js"),
  external: ["react"],
});
await build({
  ...common,
  entryPoints: ["react-dom/client"],
  outfile: path.join(outdir, "react-dom-client.js"),
  external: ["react"],
});

// echarts：自包含（zrender 已内联）
await build({
  ...common,
  entryPoints: ["echarts"],
  outfile: path.join(outdir, "echarts.js"),
});

console.log("artifact vendor bundle done →", outdir);
