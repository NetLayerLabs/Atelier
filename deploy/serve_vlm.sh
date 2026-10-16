#!/usr/bin/env bash
# OPTIONAL second vLLM server for vision on :$VLM_PORT (default 8001), localhost only by default.
#
# Not needed in the default plan: google/gemma-4-26B-A4B-it (serve_llm.sh) reads images itself, so
# AMD_VISION_ENDPOINT points at the LLM server and this script does nothing unless VLM_MODEL is set.
# Only start a separate vision server if you want vision isolated from the brain, e.g.
#   VLM_MODEL=google/gemma-4-12B-it ./deploy/serve_vlm.sh         # smaller Gemma 4, ~24 GB BF16 (estimate)
#   VLM_MODEL=Qwen/Qwen3-VL-8B-Instruct ./deploy/serve_vlm.sh     # the pre-v6 vision model
. "$(dirname "$0")/common.sh"

if [ -z "${VLM_MODEL:-}" ]; then
  echo "serve_vlm.sh: VLM_MODEL not set — nothing to do. The default plan serves vision from the LLM server"
  echo "(Gemma 4 is multimodal): AMD_VISION_ENDPOINT = AMD_VLLM_ENDPOINT. See docs/AMD_SETUP.md."
  exit 0
fi
: "${VLLM_API_KEY:?Set VLLM_API_KEY in deploy/.env (openssl rand -hex 24)}"

IMAGE="${VLLM_IMAGE:-vllm/vllm-openai-rocm:v0.31.0}"
MODEL="$VLM_MODEL"
PORT="${VLM_PORT:-8001}"
BIND="${VLM_BIND:-127.0.0.1}"
NAME=atelier-vlm

model_lc=$(printf '%s' "$MODEL" | tr '[:upper:]' '[:lower:]')
case "$model_lc" in
  *gemma-4*) D_MM='{"image": 4, "audio": 0}'
             D_TEMPLATE=/srv/deploy/templates/tool_chat_template_gemma4.jinja; D_REASON=gemma4 ;;
  *)         D_MM='{"image": 4}'; D_TEMPLATE=""; D_REASON="" ;;
esac
LIMIT_MM="${VLM_LIMIT_MM-$D_MM}"
CHAT_TEMPLATE="${VLM_CHAT_TEMPLATE-$D_TEMPLATE}"
REASONING_PARSER="${VLM_REASONING_PARSER-$D_REASON}"

args=(serve "$MODEL" --host "$BIND" --port "$PORT" --api-key "$VLLM_API_KEY"
  --gpu-memory-utilization "${VLM_GPU_UTIL:-0.18}" --max-model-len "${VLM_MAX_MODEL_LEN:-16384}")
[ -n "$LIMIT_MM" ] && args+=(--limit-mm-per-prompt "$LIMIT_MM")
args+=("${VLLM_MEDIA_ARGS[@]}")  # no URL fetching: images arrive as data: URLs (common.sh)
[ -n "$CHAT_TEMPLATE" ] && args+=(--chat-template "$CHAT_TEMPLATE")
[ -n "$REASONING_PARSER" ] && args+=(--reasoning-parser "$REASONING_PARSER")
# shellcheck disable=SC2206
[ -n "${VLM_EXTRA_ARGS:-}" ] && args+=($VLM_EXTRA_ARGS)

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped "${ROCM_DOCKER_FLAGS[@]}" \
  -v "$HF_CACHE:/root/.cache/huggingface" -v "$DEPLOY_DIR:/srv/deploy:ro" -e HF_TOKEN="${HF_TOKEN:-}" \
  -e VLLM_ROCM_USE_AITER="${VLLM_ROCM_USE_AITER:-1}" "${VLLM_MEDIA_ENV[@]}" \
  --entrypoint vllm "$IMAGE" "${args[@]}"

wait_http "http://127.0.0.1:$PORT/v1/models" "Authorization: Bearer $VLLM_API_KEY" 1800 "$NAME"
echo "VLM up: $MODEL on :$PORT (bind $BIND). Point AMD_VISION_ENDPOINT at it. Logs: docker logs -f $NAME"
