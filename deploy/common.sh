# Shared helpers for deploy/serve_*.sh (sourced, not executed).
set -euo pipefail
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$DEPLOY_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$DEPLOY_DIR/.env"
  set +a
fi

HF_CACHE="${HF_CACHE:-/root/.cache/huggingface}"
mkdir -p "$HF_CACHE"

# Flags from the ROCm docs for GPU access inside Docker on Instinct GPUs.
ROCM_DOCKER_FLAGS=(--device /dev/kfd --device /dev/dri --group-add video --ipc=host --network=host
  --cap-add=SYS_PTRACE --security-opt seccomp=unconfined --shm-size 16g)

# The model servers never fetch URLs (QA M6). The backend always sends images as base64 data: URLs (it fetches remote
# images itself through services/safe_fetch.py: https only, public addresses, redirects re-checked). vLLM treats an
# EMPTY --allowed-media-domains as "allow every host", so we pin it to a reserved name that never resolves
# (RFC 2606 ".invalid"): any http(s) image URL in a request is refused, data: URLs still work, file: URLs stay off
# (no --allowed-local-media-path). Redirects are off too, should someone widen the list. Override only if a client
# you trust (e.g. an Evolus workflow) must pass image URLs: VLLM_ALLOWED_MEDIA_DOMAINS="cdn.example.com".
# shellcheck disable=SC2206  # space-separated list on purpose (the flag takes one or more hosts)
VLLM_MEDIA_ARGS=(--allowed-media-domains ${VLLM_ALLOWED_MEDIA_DOMAINS:-media.invalid})
VLLM_MEDIA_ENV=(-e VLLM_MEDIA_URL_ALLOW_REDIRECTS=0)

# wait_http URL [AUTH_HEADER] [TIMEOUT_S] [CONTAINER]
wait_http() {
  local url="$1" auth="${2:-}" timeout="${3:-1200}" container="${4:-}" start
  start=$(date +%s)
  echo "Waiting for $url (model download + load can take several minutes)…"
  while true; do
    if [ -n "$auth" ]; then code=$(curl -s -o /dev/null -w '%{http_code}' -H "$auth" "$url" || true)
    else code=$(curl -s -o /dev/null -w '%{http_code}' "$url" || true); fi
    if [ "$code" = "200" ]; then echo "Ready: $url"; return 0; fi
    if [ -n "$container" ] && [ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" != "true" ]; then
      echo "Container $container stopped. Last logs:"; docker logs --tail 60 "$container" || true; return 1
    fi
    if [ $(( $(date +%s) - start )) -gt "$timeout" ]; then
      echo "Timed out after ${timeout}s. Last logs:"; [ -n "$container" ] && docker logs --tail 60 "$container"; return 1
    fi
    sleep 5
  done
}
