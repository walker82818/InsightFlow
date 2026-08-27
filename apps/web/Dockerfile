# InsightFlow Web — Next.js standalone image (monorepo / pnpm workspace).
#
# Build from the REPOSITORY ROOT so pnpm workspace deps resolve:
#   docker build -f apps/web/Dockerfile -t insightflow-web .
#
# The runtime image is a slim Node server running the compiled standalone app;
# Next's outputFileTracing bundles the server + its traced node_modules.
FROM node:20-alpine AS deps
WORKDIR /repo
RUN apk add --no-cache libc6-compat
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
# Prefetch the two workspace packages' manifests so pnpm install resolves.
COPY packages/chart-schema/package.json packages/chart-schema/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

# ---- Builder: compile the Next.js app ----
FROM node:20-alpine AS builder
WORKDIR /repo
RUN corepack enable
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_OUTPUT_STANDALONE=1
# Next's rewrites are evaluated at build time; bake in the backend target so the
# standalone server proxies /api to the `api` compose service at runtime.
ARG BACKEND_URL=http://api:8000
ENV BACKEND_URL=${BACKEND_URL}
# Inline API base for the browser (empty = same-origin via the Next proxy).
# Set to a browser-reachable backend URL only when the proxy cannot be used.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN cd apps/web && pnpm build

# ---- Runner: minimal production server ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 1001 -S nodejs \
    && adduser -S nextjs -u 1001

# Copy the standalone server output (already includes traced node_modules).
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
# Copy static assets + public dir.
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "apps/web/server.js"]
