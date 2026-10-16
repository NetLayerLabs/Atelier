#!/usr/bin/env bash
# Start the servers in order (each waits for the previous to finish loading, so vLLM's memory profiling sees a
# stable picture): Gemma 4 (text + vision) -> [optional separate VLM, only if VLM_MODEL is set] -> FLUX diffusion.
set -euo pipefail
cd "$(dirname "$0")"
./serve_llm.sh
[ "${SKIP_VLM:-0}" = "1" ] || ./serve_vlm.sh   # no-op unless VLM_MODEL is set (default: vision on the LLM server)
./serve_diffusion.sh
command -v rocm-smi >/dev/null && rocm-smi --showmeminfo vram || true
echo "All servers up. On your laptop: ./deploy/tunnel.sh <droplet-ip>"
