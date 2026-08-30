import path from "path";
import type { NextConfig } from "next";

// Backend target for the dev proxy. Override via BACKEND_URL if needed.
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Production container build (see apps/web/Dockerfile). Standalone bundles the
  // server + its minimal node_modules so the image can be tiny and start fast.
  output: "standalone",
  // monorepo root so Next's standalone tracing can follow the pnpm workspace
  // deps (@insightflow/*) when building the Docker image.
  outputFileTracingRoot: path.join(__dirname, "..", ".."),
  transpilePackages: [
    "@insightflow/artifact-schema",
    "@insightflow/chart-schema",
    "@insightflow/shared-types",
  ],
  // apps/web ships its own .git, so point Turbopack's resolution root at the
  // monorepo root where pnpm hoists node_modules. Keeps the workspace working
  // without altering the nested git repo.
  turbopack: { root: path.resolve(__dirname, "..", "..") },
  // Allow the IDE preview pane (which loads the page from 127.0.0.1:3000) to
  // fetch Next dev resources (HMR + JS chunks). Without this, Next 16 blocks
  // those cross-origin requests and the client bundle never loads, so the page
  // stays on its initial "detecting…" state forever.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Proxy API + health to the backend so the browser can talk same-origin when
  // NEXT_PUBLIC_API_URL is left empty. NOTE: Next's rewrites proxy buffers the
  // response, which breaks SSE streaming for the /run endpoint. For streaming we
  // therefore set NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 in .env.local so the
  // browser connects to the backend directly (no proxy, no buffering). This
  // rewrite block is only a same-origin fallback for non-streaming calls.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/health", destination: `${BACKEND}/health` },
      { source: "/health/:path*", destination: `${BACKEND}/health/:path*` },
    ];
  },
};

export default nextConfig;
