"""v6: Gemma 4 on AMD - robust JSON extraction, vision image capping / format, check_amd against the fake vLLM."""

import asyncio
import json

import pytest

from app.services import http, openai_compat, telemetry, vision
from app.services.openai_compat import extract_json, is_gemma4, strip_reasoning, thinking_disabled
from fake_upstreams import FAKE_LLM_MODEL, RoutingTransport, create_openai_app, tiny_png
from scripts import check_amd

VLLM = "vllm.fake:8000"

# --------------------------------------------------------------------------- extract_json


GOOD = {"garment": "jacket", "fabrics": ["denim", "twill"], "retailPriceUsd": 389}


@pytest.mark.parametrize("raw", [
    # Gemma 4 thought channel leaked into content (vllm#39043), with braces inside the thought
    '<|channel>thought\nThe user wants {a jacket}. I will output [JSON].<channel|>' + json.dumps(GOOD),
    # empty thought block emitted by the template when thinking is off
    '<|channel>thought\n<channel|>' + json.dumps(GOOD),
    # unterminated thought block (closing tag eaten)
    '<|channel>thought\nlet me think about this…\n' + json.dumps(GOOD),
    # Qwen / DeepSeek style
    '<think>\nreasoning with {"partial": 1}\n</think>\n\n' + json.dumps(GOOD),
    # stray control tags around a fenced answer
    '<|think|>\n```json\n' + json.dumps(GOOD) + '\n```<turn|>',
    # leaked tool-call markup before the answer
    '<|tool_call>call:lookup{q:"denim"}<tool_call|>' + json.dumps(GOOD),
    # prose with a small JSON-ish list before the real object, plus a trailing comma
    'Notes: [1, 2]. Answer: {"garment": "jacket", "fabrics": ["denim", "twill"], "retailPriceUsd": 389,}',
    # trailing junk after the object
    json.dumps(GOOD) + "\n<eos>",
])
def test_extract_json_survives_leaked_reasoning_and_tags(raw):
    assert extract_json(raw) == GOOD


def test_extract_json_keeps_plain_html_like_text_inside_strings():
    data = {"body": "Dear team,<br>please quote <b>FOB</b>.", "subject": "RFQ"}
    assert extract_json("<|channel>thought\nok<channel|>" + json.dumps(data)) == data


def test_extract_json_still_rejects_non_json():
    with pytest.raises(ValueError):
        extract_json("<|channel>thought\nno answer<channel|>Sorry, I cannot help with that.")
    with pytest.raises(ValueError):
        extract_json('{"unterminated": [1, 2')


def test_strip_reasoning_and_helpers():
    assert strip_reasoning("<|channel>thought\nhmm<channel|>hello<turn|>") == "hello"
    assert is_gemma4("google/gemma-4-26B-A4B-it") and is_gemma4("fake/gemma-4-26B-A4B-it")
    assert not is_gemma4("Qwen/Qwen3.6-35B-A3B") and not is_gemma4("google/gemma-3-27b-it") and not is_gemma4("")
    assert thinking_disabled({"chat_template_kwargs": {"enable_thinking": False}})
    assert not thinking_disabled({}) and not thinking_disabled({"chat_template_kwargs": {"enable_thinking": True}})


def test_env_example_turns_gemma_thinking_off():
    from pathlib import Path

    env = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    line = next(x for x in env.splitlines() if x.startswith("ATELIER_LLM_EXTRA_BODY="))
    assert thinking_disabled(json.loads(line.split("=", 1)[1]))


# --------------------------------------------------------------------------- vision: format + cap


def _imgs(n: int) -> list[vision.ImageInput]:
    return [vision.ImageInput(public_url=f"http://testserver/static/uploads/{i}.png", data=tiny_png(),
                              content_type="image/png") for i in range(n)]


def test_vision_messages_are_openai_image_url_parts_images_first():
    msgs = vision.vision_messages(_imgs(3), 0)
    content = msgs[-1]["content"]
    assert [p["type"] for p in content] == ["image_url"] * 3 + ["text"]
    assert all(p["image_url"]["url"].startswith("data:image/png;base64,") for p in content[:3])


def test_vision_caps_images_per_prompt(s, monkeypatch):
    assert len(vision.images_for_prompt(_imgs(6))) == 4
    assert len(vision.images_for_prompt(_imgs(3))) == 3
    monkeypatch.setattr(s, "atelier_vision_max_images", 2)
    assert len(vision.images_for_prompt(_imgs(6))) == 2


@pytest.mark.real_vision
def test_upload_of_six_reads_four_and_says_so(client, s, monkeypatch):
    fake = create_openai_app(api_key="k1")
    http.set_transport(RoutingTransport({VLLM: fake}))
    monkeypatch.setattr(s, "amd_vision_endpoint", f"http://{VLLM}/v1")
    monkeypatch.setattr(s, "amd_vllm_api_key", "k1")
    files = [("images", (f"{i}.png", tiny_png(), "image/png")) for i in range(6)]
    r = client.post("/api/trends/analyze", files=files)
    assert r.status_code == 200, r.text
    by = r.json()["analyzedBy"]
    assert by["imagesAnalyzed"] == 4 and by["imagesSubmitted"] == 6
    assert by["model"] == FAKE_LLM_MODEL
    sent = fake.state.requests[-1]["messages"][-1]["content"]
    assert sum(p["type"] == "image_url" for p in sent) == 4
    assert len(r.json()["sourceImageUrls"]) == 6


@pytest.mark.real_vision
def test_vision_parses_through_leaked_gemma_thoughts(client, s, monkeypatch):
    http.set_transport(RoutingTransport({VLLM: create_openai_app(leak_reasoning=True)}))
    monkeypatch.setattr(s, "amd_vision_endpoint", f"http://{VLLM}/v1")
    r = client.post("/api/trends/analyze", files=[("images", ("a.png", tiny_png(), "image/png"))])
    assert r.status_code == 200, r.text
    assert r.json()["trendName"] == "Fake Indigo Utility"
    calls = [c for c in telemetry.snapshot().calls if c.service == "vision"]
    assert calls[0].ok and calls[0].attempt == 1  # parsed on the first try, no retry needed


# --------------------------------------------------------------------------- check_amd against the fake vLLM


def _run_check(capsys, fake, *, image: bool, tools: bool = False) -> tuple[bool, str]:
    http.set_transport(RoutingTransport({VLLM: fake}))
    ok = asyncio.run(check_amd.check_chat("llm", f"http://{VLLM}/v1", "", "k1", image=image, tools=tools))
    return ok, capsys.readouterr().out


def test_check_amd_llm_gemma_json_and_tool_round_trip(s, capsys, monkeypatch):
    monkeypatch.setattr(s, "atelier_llm_extra_body", '{"chat_template_kwargs": {"enable_thinking": false}}')
    fake = create_openai_app(api_key="k1")
    ok, out = _run_check(capsys, fake, image=False, tools=True)
    assert ok, out
    # the double reports a gemma-4 id, but a fake never earns the Gemma verdict
    assert "WARN  gemma-4" in out and "TEST DOUBLE" in out and "counts for" not in out
    assert "thinking: off" in out
    assert "PASS  json" in out and "tok/s" in out and FAKE_LLM_MODEL in out
    assert "PASS  tools" in out and "get_fabric_price" in out and "(2 turns)" in out
    # thinking off was sent on the JSON call and on both tool turns
    assert all(b.get("chat_template_kwargs") == {"enable_thinking": False} for b in fake.state.requests)
    tool_turns = [b for b in fake.state.requests if b.get("tools")]
    assert len(tool_turns) == 2 and tool_turns[1]["messages"][-1]["role"] == "tool"


def test_gemma_verdict_for_real_ids():
    ok, msg = check_amd.gemma_verdict("google/gemma-4-26B-A4B-it")
    assert ok and "Gemma 4 (Google, open)" in msg
    assert not check_amd.gemma_verdict("Qwen/Qwen3.6-35B-A3B")[0]
    assert not check_amd.gemma_verdict("google/gemma-4-26B-A4B-it", fake=True)[0]


def test_check_amd_warns_when_not_gemma(s, capsys, monkeypatch):
    monkeypatch.setattr(s, "atelier_llm_extra_body", "")
    ok, out = _run_check(capsys, create_openai_app(api_key="k1", model="Qwen/Qwen3.6-35B-A3B"), image=False)
    assert ok, out  # a warning, not a failure
    assert "WARN  gemma-4" in out
    assert "WARN  thinking" in out


def test_check_amd_vision_one_image(s, capsys):
    fake = create_openai_app(api_key="k1")
    ok, out = _run_check(capsys, fake, image=True)
    assert ok, out
    assert "PASS  image" in out
    parts = fake.state.requests[-1]["messages"][0]["content"]
    assert [p["type"] for p in parts] == ["image_url", "text"]


def test_check_amd_fails_cleanly_without_a_tool_call(s, capsys):
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/v1/models")
    async def models():
        return {"data": [{"id": "google/gemma-4-26B-A4B-it", "object": "model"}], "object": "list"}

    @app.post("/v1/chat/completions")
    async def chat():
        return {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                "choices": [{"index": 0, "message": {"role": "assistant",
                                                     "content": '<|tool_call>call:get_fabric_price{}<tool_call|>'},
                             "finish_reason": "stop"}]}

    http.set_transport(RoutingTransport({VLLM: app}))
    client = openai_compat.make_client(f"http://{VLLM}/v1", "", 5)
    ok = asyncio.run(check_amd.check_tools(client, "google/gemma-4-26B-A4B-it"))
    out = capsys.readouterr().out
    assert not ok and "FAIL  tools" in out and "--tool-call-parser" in out
