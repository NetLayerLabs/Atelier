# Runtime-only image: the Next.js standalone build is made off the VPS (no build here, so no memory spike).
FROM node:22-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3100 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --chown=node:node standalone/ ./
COPY --chown=node:node static/ ./.next/static/
COPY --chown=node:node public/ ./public/
USER node
EXPOSE 3100
HEALTHCHECK --interval=10s --timeout=4s --start-period=15s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3100/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "server.js"]
