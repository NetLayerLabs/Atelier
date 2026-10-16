#!/usr/bin/env bash
# Serve THE model with vLLM (ROCm) on the AMD GPU box. OpenAI-compatible API on :$LLM_PORT (default 8000).
# Default plan (CONTRACT.md "v6"): ONE server, google/gemma-4-26B-A4B-it, used for BOTH the text brain and vision
# (Gemma 4 takes text + images), and as the Evolus workspace model. Public by default because Evolus (cloud) must
# reach it; always protected by --api-key.
#   ./deploy/serve_llm.sh                                   # uses deploy/.env
#   LLM_MODEL=Qwen/Qwen3.6-35B-A3B ./deploy/serve_llm.sh    # alternative family; parsers are picked per family
. "$(dirname "$0")/common.sh"
: "${VLLM_API_KEY:?Set VLLM_API_KEY in deploy/.env (openssl rand -hex 24)}"

IMAGE="${VLLM_IMAGE:-vllm/vllm-openai-rocm:v0.31.0}"
MODEL="${LLM_MODEL:-google/gemma-4-26B-A4B-it}"
PORT="${LLM_PORT:-8000}"
BIND="${LLM_BIND:-0.0.0.0}"
NAME=atelier-llm

# Per-family defaults (each can be overridden in deploy/.env; set a variable to "" to drop the flag).
model_lc=$(printf '%s' "$MODEL" | tr '[:upper:]' '[:lower:]')
case "$model_lc" in
  *gemma-4*)
    # recipes.vllm.ai/Google/gemma-4-31B-it: gemma4 tool + reasoning parsers, the gemma4 tool chat template.
    FAMILY=gemma4; MIN_VLLM=0.19.1
    D_TOOL=gemma4; D_REASON=gemma4; D_TEMPLATE=/srv/deploy/templates/tool_chat_template_gemma4.jinja
    D_MM='{"image": 4, "audio": 0}' ;;
  *qwen3*)
    FAMILY=qwen3; MIN_VLLM=""
    D_TOOL=qwen3_coder; D_REASON=qwen3; D_TEMPLATE=""; D_MM='{"image": 4}' ;;
  *)
    FAMILY=other; MIN_VLLM=""
    D_TOOL=hermes; D_REASON=""; D_TEMPLATE=""; D_MM="" ;;
esac
TOOL_PARSER="${LLM_TOOL_PARSER-$D_TOOL}"
REASONING_PARSER="${LLM_REASONING_PARSER-$D_REASON}"
CHAT_TEMPLATE="${LLM_CHAT_TEMPLATE-$D_TEMPLATE}"
LIMIT_MM="${LLM_LIMIT_MM-$D_MM}"

# Gemma 4 needs vLLM >= 0.19.1. Ask the image itself (SKIP_VLLM_VERSION_CHECK=1 to skip).
if [ -n "$MIN_VLLM" ] && [ "${SKIP_VLLM_VERSION_CHECK:-0}" != "1" ]; then
  echo "Checking the vLLM version in $IMAGE (needs >= $MIN_VLLM for $MODEL)…"
  have=$(docker run --rm --entrypoint python3 "$IMAGE" -c 'import vllm; print(vllm.__version__)' 2>/dev/null \
    | tail -1 | sed -E 's/^v//; s/[^0-9.].*$//')
  if [ -z "$have" ]; then
    echo "Could not read vllm.__version__ from $IMAGE. Pick a tag >= v$MIN_VLLM (docs/AMD_SETUP.md) or set SKIP_VLLM_VERSION_CHECK=1."; exit 1
  fi
  if [ "$(printf '%s\n%s\n' "$MIN_VLLM" "$have" | sort -V | head -1)" != "$MIN_VLLM" ]; then
    echo "$IMAGE ships vLLM $have; $MODEL needs >= $MIN_VLLM. Set VLLM_IMAGE to a newer tag."; exit 1
  fi
  echo "vLLM $have OK"
fi

args=(serve "$MODEL" --host "$BIND" --port "$PORT" --api-key "$VLLM_API_KEY"
  --gpu-memory-utilization "${LLM_GPU_UTIL:-0.60}" --max-model-len "${LLM_MAX_MODEL_LEN:-32768}")
[ -n "$TOOL_PARSER" ] && args+=(--enable-auto-tool-choice --tool-call-parser "$TOOL_PARSER")
[ -n "$REASONING_PARSER" ] && args+=(--reasoning-parser "$REASONING_PARSER")
[ -n "$CHAT_TEMPLATE" ] && args+=(--chat-template "$CHAT_TEMPLATE")
[ -n "$LIMIT_MM" ] && args+=(--limit-mm-per-prompt "$LIMIT_MM")
args+=("${VLLM_MEDIA_ARGS[@]}")  # no URL fetching: images arrive as data: URLs (common.sh)
# shellcheck disable=SC2206
[ -n "${LLM_EXTRA_ARGS:-}" ] && args+=($LLM_EXTRA_ARGS)

echo "Model family: $FAMILY · tool parser: ${TOOL_PARSER:-none} · reasoning parser: ${REASONING_PARSER:-none}"
echo "vllm ${args[*]/$VLLM_API_KEY/<VLLM_API_KEY>}"

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped "${ROCM_DOCKER_FLAGS[@]}" \
  -v "$HF_CACHE:/root/.cache/huggingface" -v "$DEPLOY_DIR:/srv/deploy:ro" -e HF_TOKEN="${HF_TOKEN:-}" \
  -e VLLM_ROCM_USE_AITER="${VLLM_ROCM_USE_AITER:-1}" "${VLLM_MEDIA_ENV[@]}" \
  --entrypoint vllm "$IMAGE" "${args[@]}"

wait_http "http://127.0.0.1:$PORT/v1/models" "Authorization: Bearer $VLLM_API_KEY" 1800 "$NAME"
curl -s -H "Authorization: Bearer $VLLM_API_KEY" "http://127.0.0.1:$PORT/v1/models"; echo
echo "LLM up: $MODEL on :$PORT (bind $BIND). Logs: docker logs -f $NAME"
case "$model_lc" in *gemma-4*) echo "One server for text + vision: point AMD_VLLM_ENDPOINT and AMD_VISION_ENDPOINT at it." ;; esac
