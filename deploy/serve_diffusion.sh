#!/usr/bin/env bash
# Serve deploy/diffusion_server.py (diffusers on PyTorch ROCm) on :$DIFFUSION_PORT (default 8002), localhost only.
# Start it AFTER the vLLM servers: vLLM sizes its KV cache from free memory at startup.
. "$(dirname "$0")/common.sh"

IMAGE="${TORCH_IMAGE:-rocm/pytorch:rocm10.1.0_ubuntu24.04_py3.12_pytorch_release_2.13.0}"
PORT="${DIFFUSION_PORT:-8002}"
BIND="${DIFFUSION_BIND:-127.0.0.1}"
NAME=atelier-diffusion

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped "${ROCM_DOCKER_FLAGS[@]}" \
  -v "$HF_CACHE:/root/.cache/huggingface" -v "$DEPLOY_DIR:/srv/deploy:ro" \
  -e HF_TOKEN="${HF_TOKEN:-}" -e DIFFUSION_MODEL="${DIFFUSION_MODEL:-black-forest-labs/FLUX.1-schnell}" \
  -e DIFFUSION_API_KEY="${DIFFUSION_API_KEY:-}" -e DIFFUSION_STEPS="${DIFFUSION_STEPS:-}" \
  -e DIFFUSION_GUIDANCE="${DIFFUSION_GUIDANCE:-}" \
  "$IMAGE" bash -lc "
    set -e
    python -c 'import torch; assert torch.version.hip, \"not a ROCm torch build\"; print(\"torch\", torch.__version__, \"hip\", torch.version.hip, torch.cuda.get_device_name(0))'
    pip install --quiet -r /srv/deploy/requirements-diffusion.txt
    exec python -m uvicorn diffusion_server:app --app-dir /srv/deploy --host $BIND --port $PORT
  "

# /health answers while the model loads; wait until it reports "ok".
start=$(date +%s)
echo "Waiting for the diffusion model to load…"
until curl -s "http://127.0.0.1:$PORT/health" | grep -q '"status":"ok"'; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]; then
    echo "Container stopped:"; docker logs --tail 60 "$NAME"; exit 1; fi
  if curl -s "http://127.0.0.1:$PORT/health" | grep -q '"status":"error"'; then
    curl -s "http://127.0.0.1:$PORT/health"; echo; docker logs --tail 40 "$NAME"; exit 1; fi
  [ $(( $(date +%s) - start )) -gt 1800 ] && { echo "Timed out"; docker logs --tail 60 "$NAME"; exit 1; }
  sleep 5
done
curl -s "http://127.0.0.1:$PORT/health"; echo
echo "Diffusion up on :$PORT (bind $BIND). Logs: docker logs -f $NAME"
