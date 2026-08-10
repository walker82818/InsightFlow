import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@insightflow/chart-schema", "@insightflow/shared-types"],
  // apps/web ships its own .git, so point Turbopack's resolution root at the
  // monorepo root where pnpm hoists node_modules. Keeps the workspace working
  // without altering the nested git repo.
  turbopack: { root: path.resolve(__dirname, "..", "..") },
};

export default nextConfig;
