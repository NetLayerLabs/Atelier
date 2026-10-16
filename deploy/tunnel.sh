#!/usr/bin/env bash
# Run ON YOUR LAPTOP. Forwards the GPU box's servers to local ports that don't collide with
# Atelier (8787/3100), Next.js (3000) or a local 8000:
#   localhost:18000 -> box:8000 (Gemma 4: text + vision)   localhost:18002 -> box:8002 (diffusion)
#   localhost:18001 -> box:8001 (optional separate VLM, only if you started serve_vlm.sh with VLM_MODEL)
#
#   ./deploy/tunnel.sh 203.0.113.10                 # root@, default key
#   AMD_SSH_KEY=~/.ssh/amd ./deploy/tunnel.sh 203.0.113.10
set -euo pipefail
HOST="${1:-${AMD_HOST:-}}"
[ -n "$HOST" ] || { echo "usage: $0 <droplet-ip>   (or set AMD_HOST)"; exit 2; }
USER_="${AMD_USER:-root}"
L_LLM="${LOCAL_LLM_PORT:-18000}"; L_VLM="${LOCAL_VLM_PORT:-18001}"; L_DIF="${LOCAL_DIFFUSION_PORT:-18002}"
R_LLM="${LLM_PORT:-8000}"; R_VLM="${VLM_PORT:-8001}"; R_DIF="${DIFFUSION_PORT:-8002}"

for p in "$L_LLM" "$L_VLM" "$L_DIF"; do
  if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Local port $p is busy (another tunnel?). Free it or set LOCAL_*_PORT."; exit 1; fi
done

cat <<EOF
Tunnel to $USER_@$HOST. Put this in backend/.env:

  AMD_VLLM_ENDPOINT=http://127.0.0.1:$L_LLM/v1
  AMD_VISION_ENDPOINT=http://127.0.0.1:$L_LLM/v1     # same Gemma 4 server (or :$L_VLM if you run a separate VLM)
  AMD_DIFFUSION_ENDPOINT=http://127.0.0.1:$L_DIF/generate
  AMD_VLLM_API_KEY=<VLLM_API_KEY from deploy/.env>
  ATELIER_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
  AMD_GPU_LABEL=AMD Instinct MI300X                   # only if that is what rocm-smi shows

Then: cd backend && uv run python scripts/check_amd.py
Ctrl+C closes the tunnel. Reconnects are on you (or use autossh with the same -L flags).
EOF

exec ssh -N -o ServerAliveInterval=20 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
  ${AMD_SSH_KEY:+-i "$AMD_SSH_KEY"} \
  -L "$L_LLM:127.0.0.1:$R_LLM" -L "$L_VLM:127.0.0.1:$R_VLM" -L "$L_DIF:127.0.0.1:$R_DIF" \
  "$USER_@$HOST"
