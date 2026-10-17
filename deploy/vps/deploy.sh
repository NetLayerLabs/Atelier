#!/usr/bin/env bash
# Deploy Atelier to a shared VPS without building Next.js there (no memory spike next to other services).
#
#   VPS=root@203.0.113.10 HOST=atelier.example.com deploy/vps/deploy.sh
#
# Needs: backend/.env.vps (backend/.env plus ATELIER_ADMIN_TOKEN, PUBLIC_BASE_URL=https://$HOST,
# CORS_ORIGINS=https://$HOST), docker compose on the VPS, and nginx-atelier.conf installed once (see that file).
# Both containers listen on 127.0.0.1:8870 / 8871 only and are memory-capped (docker-compose.yml).
set -euo pipefail

: "${VPS:?set VPS=user@host}"
: "${HOST:?set HOST=the public hostname}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/opt/atelier
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "1/4 building the dashboard (API: ${API_BASE:-same-origin})"
rsync -a --exclude node_modules --exclude .next "$ROOT/frontend/" "$WORK/frontend/"
# same-origin: nginx serves /api and /static on the dashboard's own host, so the build works under every domain
# pointed at the server (e.g. a custom domain and the sslip.io fallback).
(cd "$WORK/frontend" && pnpm install --frozen-lockfile >/dev/null && NEXT_PUBLIC_API_BASE="${API_BASE:-same-origin}" pnpm build >/dev/null)
mkdir -p "$WORK/frontend-dist"
cp "$ROOT/deploy/vps/frontend-dist/Dockerfile" "$WORK/frontend-dist/"
cp -R "$WORK/frontend/.next/standalone" "$WORK/frontend-dist/standalone"
cp -R "$WORK/frontend/.next/static" "$WORK/frontend-dist/static"
cp -R "$WORK/frontend/public" "$WORK/frontend-dist/public"
rm -rf "$WORK"/frontend-dist/standalone/node_modules/.pnpm/@img+sharp-darwin-* # unused native image optimiser

echo "2/4 uploading to $VPS:$REMOTE"
ssh "$VPS" "mkdir -p $REMOTE && chmod 700 $REMOTE"
rsync -az --delete --exclude .venv --exclude var --exclude '.env*' --exclude tests --exclude __pycache__ \
  --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude 'static/uploads/*' --exclude 'static/generated/*' \
  --exclude 'static/quotes/*' "$ROOT/backend/" "$VPS:$REMOTE/backend/"
rsync -az --delete "$WORK/frontend-dist/" "$VPS:$REMOTE/frontend-dist/"
rsync -az "$ROOT/deploy/vps/docker-compose.yml" "$VPS:$REMOTE/docker-compose.yml"
scp -q "$ROOT/backend/.env.vps" "$VPS:$REMOTE/backend.env"
ssh "$VPS" "chmod 600 $REMOTE/backend.env"

echo "3/4 building images (low priority) and starting"
ssh "$VPS" "cd $REMOTE && nice -n 15 docker compose build >/dev/null && docker compose up -d"

echo "4/4 checking https://$HOST"
for _ in $(seq 1 30); do curl -sf "https://$HOST/api/health" >/dev/null && break; sleep 2; done
curl -s -o /dev/null -w "dashboard %{http_code}\n" "https://$HOST/"
curl -s -o /dev/null -w "api %{http_code}\n" "https://$HOST/api/health"
