# Atelier dashboard (Next.js, standalone output).
#
# NEXT_PUBLIC_API_BASE is inlined into the browser bundle at BUILD time, so it is a build arg,
# not a runtime env var. It must be the backend URL as the *browser* sees it:
#   docker build -t atelier-frontend --build-arg NEXT_PUBLIC_API_BASE=http://localhost:8787 frontend/
# To point the dashboard at a different backend, rebuild with another value.

FROM node:22-slim AS base
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH" NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
ARG NEXT_PUBLIC_API_BASE=http://localhost:8787
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build && mkdir -p public

FROM node:22-slim AS runner
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3100 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3100
HEALTHCHECK --interval=10s --timeout=4s --start-period=15s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3100/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "server.js"]
