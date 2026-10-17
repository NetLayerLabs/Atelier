# AMD setup

> **As deployed for the hackathon (17 Oct 2026): AMD Token Factory.** Atelier runs on AMD's hosted OpenAI-compatible
> API (`AMD_VISION_ENDPOINT=https://developer.amd.com.cn/radeon/api/v1`, `AMD_TOKEN_FACTORY_KEY=rc-…`,
> `AMD_VISION_MODEL=Gemma-4-31B-IT`, `AMD_GPU_LABEL="AMD GPUs (AMD Token Factory)"`). The same model is registered
> in the Evolus workspace as our own model. Limits we measured: 5 MB per request (images are downscaled first),
> 30 requests per minute per key, and a shared queue whose wait varies from 2 s to 90 s (the app sends a second,
> identical request when the first is slow). No droplet has been run yet; the rest of this guide is the self-hosted
> path for when one is available (it adds diffusion concepts and a direct vLLM backup).

## AMD Developer Cloud (self-hosted path)

This guide takes a fresh AMD Developer Cloud GPU droplet (1× AMD Instinct MI300X) to the servers Atelier uses live.
**The default plan is one open model, Gemma 4, served by our own vLLM**: it is the text brain, the vision model and
the Evolus workspace model — so the same endpoint covers the AMD track, Google's "Gemma on AMD" prize and the
Evolus "own vLLM endpoint on AMD Developer Cloud" requirement.

| Server | Default model | Port on the box | Exposure | Laptop port (tunnel) |
|---|---|---|---|---|
| Gemma 4 on vLLM (OpenAI API): text **and** vision | `google/gemma-4-26B-A4B-it` | 8000 | public with `--api-key` (Evolus must reach it) | 18000 |
| Diffusion (`deploy/diffusion_server.py`) | `black-forest-labs/FLUX.1-schnell` | 8002 | localhost only | 18002 |
| *(optional)* separate vision server | off (`VLM_MODEL` empty) | 8001 | localhost only | 18001 |

Images stay on FLUX: Gemma 4 reads images but does not generate them, and we found no open-weights Google
image-generation model to serve here, so the diffusion server is unchanged.

The laptop ports avoid 8000, 3000, 3100 and 8787. Everything is driven by `deploy/.env` (template:
[`deploy/env.example`](../deploy/env.example)).

## What is verified and what isn't

| Claim | Status |
|---|---|
| `vllm/vllm-openai-rocm:v0.31.0` exists (pushed 2026-10-04; also `latest` at time of writing) | **Checked** on Docker Hub (2026-10-14) |
| Gemma 4 needs vLLM ≥ 0.19.1; ROCm image `vllm/vllm-openai-rocm`; MI300X/MI325X/MI350X/MI355X listed | vLLM recipe, [link](https://recipes.vllm.ai/Google/gemma-4-31B-it). `serve_llm.sh` reads `vllm.__version__` from the image and refuses an older one. That v0.31.0 ≥ 0.19.1 is by version number; **not run** on an MI300X. |
| Flags `--enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 --chat-template examples/tool_chat_template_gemma4.jinja`; thinking toggled by `chat_template_kwargs.enable_thinking` | Same recipe. The template is vendored from vLLM v0.31.0 as `deploy/templates/tool_chat_template_gemma4.jinja` (it defaults `enable_thinking` to false; rendered locally with Jinja2) |
| `google/gemma-4-26B-A4B-it`: Apache-2.0, not gated, `image-text-to-text`, 25.8 B parameters in safetensors (3.8 B active, MoE), 256K context | **Checked** via the HF API + model card |
| `google/gemma-4-31B-it` (31.3 B, dense) and `google/gemma-4-12B-it` (12.0 B) exist, Apache-2.0, not gated | **Checked** via the HF API |
| Gemma 4 wants images **before** the text in a prompt, OpenAI `image_url` parts through vLLM | Model card. Atelier sends them that way. |
| Reasoning / tool tags can leak into `content` | vLLM issue #39043 (reported to us, not re-checked). Atelier's JSON extraction strips them; tested with fakes. |
| `rocm/pytorch:rocm10.1.0_ubuntu24.04_py3.12_pytorch_release_2.13.0` exists (2026-10-05) | **Checked** on Docker Hub |
| Alternative `Qwen/Qwen3.6-35B-A3B` is Apache-2.0, not gated, `image-text-to-text` | **Checked** via the HF API (pre-v6) |
| `FLUX.1-schnell` is gated "auto" (accept on HF + `HF_TOKEN`); `FLUX.2-klein-4B` is Apache-2.0 and not gated | **Checked** via the HF API |
| `diffusion_server.py` implements the backend contract | **Tested** locally with stubbed torch/diffusers (no GPU) |
| `check_amd.py` / `tunnel.sh` / the backend live paths | **Tested** against local fake servers only |
| Credits: AI Developer Portal → Member Perks → Request Cloud Credits ($100) | AMD article (2026), [link](https://www.amd.com/en/developer/resources/technical-articles/2026/deploying-hermes-agent-for-free-on-amd-developer-cloud-with-open.html) |
| 1× MI300X droplet: 192 GB HBM3, 20 vCPU, 240 GB RAM, about $1.99/h; 8× about $15.92/h | Third-party lablab tutorial, [link](https://lablab.ai/ai-tutorials/amd-developer-cloud-host-llm-vllm) |
| Quick Start images (vLLM, PyTorch, …), `ssh root@<ip>`, Jupyter on `http://<ip>` | AMD getting-started article, [link](https://www.amd.com/en/developer/resources/technical-articles/2025/how-to-get-started-on-the-amd-developer-cloud-.html) |
| Docker flags (`--device /dev/kfd --device /dev/dri --group-add video --ipc=host …`) | ROCm docs, [link](https://rocm.docs.amd.com/en/latest/how-to/rocm-for-ai/inference/benchmark-docker/vllm.html) |
| `VLLM_ROCM_USE_AITER=1` enables AMD's AITER kernels | vLLM env-var docs, [link](https://docs.vllm.ai/en/latest/configuration/env_vars.html) |
| `--tool-call-parser qwen3_coder` for the Qwen alternative | AMD Hermes-agent article (Qwen3.5). **Not tested.** |
| All memory and throughput figures below | **Estimates.** Nothing here was run on an MI300X. |

Nothing has been run on real AMD hardware yet. The Inference panel and `check_amd.py` report real numbers once
the servers are up. Put those numbers in the submission rather than the estimates here.

## 0. Access

1. Register for the event on lablab.ai. Sign up for the **AMD AI Developer Program** using "Sign up with AMD"
   on the event page.
2. Go to AI Developer Portal → **Member Perks** → **Request Cloud Credits** ($100). Then use "Log in/Create AMD
   Developer Cloud Account". You may need a card on file, and approval can take time, so apply early.
3. **Create a GPU droplet**: 1× MI300X, with the **vLLM Quick Start** or **ROCm** image. Add your SSH public key.
   At about $1.99/h, $100 buys roughly 50 GPU-hours, so destroy the droplet when you aren't using it.
   Check in the console whether a powered-off droplet still bills; on DigitalOcean-style clouds it usually does.
   If so, snapshot it, then destroy it.

## 1. Prepare the box

```bash
ssh root@<droplet-ip>
rocm-smi --showproductname          # copy the exact card name for AMD_GPU_LABEL
df -h                               # find the big scratch disk for the model cache
docker ps                           # Quick Start images already run a container called "rocm"; ours are separate

git clone <your-atelier-repo> && cd atelier     # or: scp -r deploy root@<ip>:~/atelier/
cp deploy/env.example deploy/.env
openssl rand -hex 24                # -> VLLM_API_KEY in deploy/.env
nano deploy/.env                    # VLLM_API_KEY, HF_TOKEN, HF_CACHE (on the scratch disk)
```

For FLUX.1-schnell, accept the license at https://huggingface.co/black-forest-labs/FLUX.1-schnell with the
account that owns `HF_TOKEN`. If you'd rather skip that, set `DIFFUSION_MODEL=black-forest-labs/FLUX.2-klein-4B`
(not gated; needs a diffusers release with `Flux2KleinPipeline`), or `stabilityai/stable-diffusion-xl-base-1.0`
with `DIFFUSION_STEPS=30`.

**Firewall.** The scripts use `--network=host`, so each server binds exactly where `*_BIND` says. Docker port
publishing (`-p`) bypasses ufw, but we don't use it. Only the LLM is public, because Evolus has to reach it:

```bash
ufw allow 22/tcp && ufw allow 8000/tcp && ufw --force enable
```

Port 8000 should be reachable by Evolus and nothing else. If Evolus publishes its egress IPs (ask them; we don't
have a list), allow only those instead of `8000/tcp` from anywhere, e.g.
`ufw allow from <evolus-egress-ip> to any port 8000 proto tcp` per address. The backend never needs the public port:
it talks to the box over the SSH tunnel (`deploy/tunnel.sh`). Without an IP list, `--api-key` is the only gate, so
keep the key long and random (`openssl rand -hex 24`) and rotate it if it leaks.

**No URL fetching.** A multimodal vLLM will download any `http(s)` image URL a caller puts in a request, which
would let anyone holding the key make the box fetch internal or arbitrary addresses. Atelier never sends URLs: the
backend fetches remote images itself (`services/safe_fetch.py`: https only, public addresses, redirects re-checked)
and sends every image as a base64 `data:` URL. So the scripts start vLLM with
`--allowed-media-domains media.invalid` (an empty list would mean "any host"; `.invalid` never resolves) and
`VLLM_MEDIA_URL_ALLOW_REDIRECTS=0`, and without `--allowed-local-media-path` (no `file:` reads). `data:` images
work as before. Set `VLLM_ALLOWED_MEDIA_DOMAINS` in `deploy/.env` only if a client you trust must pass URLs.

`--api-key` is mandatory (`serve_llm.sh` refuses to start without it). Plain HTTP means the key travels
unencrypted between Evolus and the box. If that matters to you, put Caddy in front (e.g. `<ip>.sslip.io` with
automatic TLS) and give Evolus the `https://` URL. We haven't tested that with Evolus.

## 2. The model: Gemma 4 on vLLM, `deploy/serve_llm.sh`

```bash
./deploy/serve_llm.sh              # checks the image's vLLM >= 0.19.1, starts, waits for GET /v1/models
```

With the defaults this runs (inside `vllm/vllm-openai-rocm:v0.31.0`, `--network=host`, AITER on):

```bash
vllm serve google/gemma-4-26B-A4B-it --host 0.0.0.0 --port 8000 --api-key $VLLM_API_KEY \
  --gpu-memory-utilization 0.60 --max-model-len 32768 \
  --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \
  --chat-template /srv/deploy/templates/tool_chat_template_gemma4.jinja \
  --limit-mm-per-prompt '{"image": 4, "audio": 0}' \
  --allowed-media-domains media.invalid          # + env VLLM_MEDIA_URL_ALLOW_REDIRECTS=0
```

`deploy/` is mounted read-only at `/srv/deploy`, which is where the vendored chat template comes from (so it does
not depend on the image shipping vLLM's `examples/`).

**Picking the image tag.** Gemma 4 needs vLLM ≥ 0.19.1. `v0.31.0` is pinned (checked on Docker Hub). To use
another: `docker run --rm --entrypoint python3 vllm/vllm-openai-rocm:<tag> -c 'import vllm; print(vllm.__version__)'`
must print ≥ 0.19.1 — `serve_llm.sh` does exactly this before starting (`SKIP_VLLM_VERSION_CHECK=1` skips it).
The recipe itself only lists `:latest`; pin a version tag so the box doesn't change under you.

**Why `google/gemma-4-26B-A4B-it`.**
- One model qualifies for all three tracks: AMD (served on an MI300X), Google (Gemma on AMD) and Evolus (our own
  vLLM endpoint as the workspace model).
- Mixture-of-experts: 25.8 B parameters in total but about 3.8 B active per token, so decode is fast — what
  judges see on stage.
- Text **and** image input, 256K context, tool calling (`gemma4` parser) and a thinking switch.
- Apache-2.0 and not gated: downloads without approval.
- About 52 GB of BF16 weights (25.8 B × 2 bytes, estimate), leaving plenty of the 192 GB for KV cache and FLUX.

| Option | When |
|---|---|
| `google/gemma-4-26B-A4B-it` (default) | Fast MoE, text + vision on one GPU |
| `google/gemma-4-31B-it` | Dense, probably stronger writing, slower; ~63 GB BF16 weights (estimate) — still fits |
| `google/gemma-4-12B-it` | Smaller / faster (~24 GB BF16, estimate), or as a separate vision server |
| `Qwen/Qwen3.6-35B-A3B` (alternative, **not Gemma**) | `LLM_MODEL=Qwen/Qwen3.6-35B-A3B`: the scripts switch to `--tool-call-parser qwen3_coder --reasoning-parser qwen3`. Doesn't count for the Google prize; `check_amd.py` and the landing page say so honestly. |

Parsers are chosen from the model name (`gemma-4` → `gemma4`; `qwen3` → `qwen3_coder`/`qwen3`; anything else →
`hermes`). `LLM_TOOL_PARSER`, `LLM_REASONING_PARSER`, `LLM_CHAT_TEMPLATE` and `LLM_LIMIT_MM` override them.

Other pre-v6 options (all **not Gemma**, so not for the Google prize): `Qwen/Qwen3.6-35B-A3B-FP8` if memory is
tight, `Qwen/Qwen3.5-9B` (~18 GB) on a smaller droplet, `openai/gpt-oss-120b` (text only, MXFP4).

**Thinking.** Gemma 4's chat template reads `chat_template_kwargs.enable_thinking` (false unless set). Atelier's
strict-JSON calls run with thinking off: `backend/.env` keeps
`ATELIER_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}` (already in `.env.example`; the same
key works for Qwen3). Evolus agents may turn thinking on; `--reasoning-parser gemma4` puts it in a separate
`reasoning_content` field. If reasoning or tool tags still leak into `content` (vLLM issue #39043), Atelier's JSON
extraction strips `<|channel>thought…<channel|>`, `<think>…</think>` and stray `<|…|>` tags before parsing.

For `--max-model-len 32768`: Atelier's prompts are under 4k tokens; Evolus agents with tools and library context
need more. Gemma 4 supports up to 256K if memory allows.

## 3. Vision: the same server (default), or `deploy/serve_vlm.sh` (optional)

**One server (default).** Gemma 4 reads images, so `AMD_VISION_ENDPOINT` = `AMD_VLLM_ENDPOINT` and both
`*_MODEL` vars are the same (or empty: the served model). Atelier sends each mood board as OpenAI `image_url` parts
(base64 `data:` URLs), images before the text, **at most 4 per prompt** (`ATELIER_VISION_MAX_IMAGES`, matching
`--limit-mm-per-prompt`). Preset boards have 3–4 photos; an upload of 5–6 is analysed from its first 4 and the trend
card says "read the first 4 of 6 images".

**Two servers (optional).** To keep trend reads from queueing behind tech packs, start a separate vision server:
`VLM_MODEL=google/gemma-4-12B-it ./deploy/serve_vlm.sh` (localhost :8001; `VLM_GPU_UTIL=0.18`) and point
`AMD_VISION_ENDPOINT` at `:18001`. Without `VLM_MODEL` the script does nothing, and `serve_all.sh` skips it.

## 4. Diffusion: `deploy/serve_diffusion.sh`

```bash
./deploy/serve_diffusion.sh        # after the vLLM servers; waits until /health reports "ok"
```

This runs `deploy/diffusion_server.py` in the ROCm PyTorch image and installs
`deploy/requirements-diffusion.txt`. That file deliberately leaves torch out, so pip can't replace the ROCm build.
The server loads the pipeline once, runs a warm-up generation, and serialises GPU work with a lock. It then
serves this contract:

```
POST /generate {"prompt","negative_prompt","seed","width","height"} -> {"images":[<base64 png>],"model","device","elapsedMs","steps",…}
GET  /health   -> {"status":"ok","model","device":"<torch.cuda.get_device_name(0)>",…}
```

The backend's Inference panel uses `elapsedMs` for images/sec, and `device` when `AMD_GPU_LABEL` is unset.

Or start everything in order: `./deploy/serve_all.sh`.

## 5. GPU memory budget (1× MI300X, 192 GB): estimates

vLLM's `--gpu-memory-utilization` is the fraction of **total** GPU memory each instance may take, covering weights
plus KV cache. Start the vLLM servers first and diffusion last, because vLLM sizes its KV cache from what is free
at startup.

| Server | Setting | Budget | Contents |
|---|---|---|---|
| Gemma 4 26B-A4B BF16 (text + vision) | `LLM_GPU_UTIL=0.60`, `--max-model-len 32768` | ~115 GB | ~52 GB weights (25.8 B params × 2 bytes, from the HF safetensors count) + ~60 GB KV cache, vision encoder activations and graphs |
| FLUX.1-schnell BF16 | (diffusers) | ~35-40 GB | ~24 GB transformer + ~9.5 GB T5-XXL + CLIP/VAE + activations at 768×1024 |
| **Total** | | **~150-155 GB** | of 192 GB — ~35 GB headroom |
| *(optional)* separate Gemma 4 12B vision server | `VLM_GPU_UTIL=0.18` | ~35 GB | ~24 GB weights + KV; uses most of the headroom |

All figures are **estimates** from parameter counts; nothing here was measured on an MI300X. `rocm-smi
--showmeminfo vram` after `serve_all.sh` gives the real numbers.

If anything runs out of memory:
1. Lower `LLM_GPU_UTIL` to 0.45 (~86 GB: weights + ~30 GB KV, plenty for Atelier's short prompts).
2. Lower `LLM_MAX_MODEL_LEN` to 16384. Atelier's prompts are under 4k tokens; Evolus agents with tools need more.
3. Add `--kv-cache-dtype fp8` through `LLM_EXTRA_ARGS` (about half the KV memory, per the vLLM recipe).
4. Use two droplets, with Gemma on one and diffusion on the other. It costs twice as much.

Community reports say a second vLLM instance can fail its memory profiling if both start at once. The scripts
start them one at a time.

## 6. Expected throughput: estimates, not measured

- **Gemma 4 26B-A4B, single stream.** About 3.8 B active parameters, so expect on the order of **100 tok/s**
  decode. A tech pack (about 1.5k tokens) should take roughly 10-20 s. This is an estimate; we found no published
  MI300X figure for Gemma 4.
- **Gemma 4 vision.** One mood-board read (4 images, a few hundred output tokens) should take a few seconds; image
  encoding adds to the time to first token.
- **FLUX.1-schnell, 4 steps, 768×1024.** Expect about 1-3 s per image. AMD's ROCm blog shows FLUX running on
  MI300X but publishes no timing. A 4-concept board renders in sequence, because the server lock serialises GPU
  work.

Measure the real numbers with `check_amd.py` and the Inference panel, then quote those.

## 7. Connect the laptop

```bash
./deploy/tunnel.sh <droplet-ip>     # ssh -N -L 18000:127.0.0.1:8000 -L 18001:… -L 18002:…
```

The tunnel is recommended over opening ports. The diffusion server stays off the internet, and the laptop's
traffic to Gemma is encrypted by SSH. Then in `backend/.env` (one model for text and vision):

```bash
AMD_VLLM_ENDPOINT=http://127.0.0.1:18000/v1
AMD_VLLM_API_KEY=<VLLM_API_KEY>
AMD_VLLM_MODEL=                     # empty = whatever the server serves (google/gemma-4-26B-A4B-it)
AMD_VISION_ENDPOINT=http://127.0.0.1:18000/v1      # the same Gemma 4 server (:18001 only with a separate VLM)
AMD_VISION_MODEL=
AMD_DIFFUSION_ENDPOINT=http://127.0.0.1:18002/generate
AMD_GPU_LABEL=AMD Instinct MI300X   # exactly what rocm-smi --showproductname printed
ATELIER_LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
```

```bash
cd backend && uv run python scripts/check_amd.py
```

For each endpoint, `check_amd.py` checks `/v1/models` and then:

- **gemma-4**: `PASS` when the served id contains `gemma-4`, otherwise a `WARN` (the Google prize depends on it).
- **json** (llm): one strict-JSON completion through the app's own client, with thinking off (it warns when
  `ATELIER_LLM_EXTRA_BODY` doesn't set `enable_thinking: false`).
- **tools** (llm): a tool-call round trip — the model must call `get_fabric_price`, gets the result back and
  answers. This is what Evolus's **Test connection** needs.
- **image** (vision): one image → JSON.
- **generate** (diffusion): one 512×512 image, saved to `static/generated/`.

Each line prints the model, latency, TTFT, tokens/sec from the server's `usage` (or images/sec) and `PASS`/`FAIL`.
The exit code is 0 only if everything passes (a `WARN` doesn't fail it).

## 8. Stage checklist

- 15 minutes before: run `check_amd.py`, which also warms the caches. Open the dashboard, click **System** (every
  service healthy and Live), then **Inference**.
- Keep the tunnel in `tmux`, or use `autossh -M 0` with the same `-L` flags.
- Every upstream call has a timeout: `ATELIER_LLM_TIMEOUT`, `ATELIER_VISION_TIMEOUT`, `ATELIER_DIFFUSION_TIMEOUT`,
  `ATELIER_EVOLUS_TIMEOUT`, and health probes at 2.5 s. If the GPU box dies mid-demo, requests fail honestly: a 503 with the setup hint for single requests, a step error with Retry in the pipeline, and the header shows the service as unreachable. Nothing is made up in its place.

## Troubleshooting

| Symptom | Try |
|---|---|
| vLLM container exits at start | `docker logs atelier-llm`. Try `VLLM_ROCM_USE_AITER=0`, a lower `LLM_GPU_UTIL`, or a smaller `LLM_MAX_MODEL_LEN`. |
| `HIP out of memory` on the second server | Start the servers one at a time (`serve_all.sh` does), lower `LLM_GPU_UTIL`, or drop the optional VLM. |
| `serve_llm.sh` says the image ships vLLM < 0.19.1 | Set `VLLM_IMAGE` to a newer `vllm/vllm-openai-rocm` tag (see section 2). |
| `check_amd.py` tools: "no tool call" | vLLM must run with `--enable-auto-tool-choice --tool-call-parser gemma4` (check `docker logs atelier-llm`). If `<\|tool_call>` shows in the content, the parser isn't active. |
| `check_amd.py` gemma-4: WARN | The server isn't serving a Gemma 4 model (`LLM_MODEL` in `deploy/.env`). Fine for testing; not for the Google prize. |
| `401` from `/v1/models` | `AMD_VLLM_API_KEY` doesn't match `VLLM_API_KEY`. |
| Diffusion `/health` stays `loading` | First download is about 30 GB. `docker logs -f atelier-diffusion`. A gated model needs `HF_TOKEN` and the accepted license. |
| `"not a ROCm torch build"` | Something reinstalled torch. Keep torch out of `requirements-diffusion.txt`. |
| JSON failures or slow first token | Make sure `ATELIER_LLM_EXTRA_BODY` disables thinking. Watch the `attempt` column in the Inference panel. |
