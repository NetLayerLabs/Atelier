"""v2: telemetry, the Evolus adapter (real documented API shape, async polling), health probes and honest errors.

All traffic is routed in-process to the test doubles in tests/fake_upstreams.py - no sockets, no GPUs.
v5: there is no simulated telemetry: only measured calls are recorded, and fakes are flagged `fake`.
"""

import asyncio
import json

import pytest
from conftest import DIFF, VLLM, go_live, route
from helpers import approve, wait

from app.services import evolus, openai_compat, probe, telemetry
from fake_upstreams import create_evolus_app, create_openai_app, create_shopify_app


def _wait(client, run_id, cond=lambda r: r["status"] != "running"):
    return wait(client, run_id, cond)


# --------------------------------------------------------------------------- telemetry


def test_no_calls_no_telemetry(client):
    t = client.get("/api/telemetry").json()
    assert t == {"calls": [], "services": []}


def test_aggregates_are_per_service_and_measured_only(s):
    telemetry.record(telemetry.InferenceCall(id="a", service="llm", purpose="x", latency_ms=1000,
                                             completion_tokens=400, tokens_per_sec=400.0))
    telemetry.record(telemetry.InferenceCall(id="b", service="llm", purpose="x", ok=False, latency_ms=50,
                                             error="boom"))
    rows = {r.service: r for r in telemetry.snapshot().services}
    assert rows["llm"].calls == 2 and rows["llm"].errors == 1
    assert rows["llm"].avg_tokens_per_sec == 400.0 and rows["llm"].avg_latency_ms == 1000
    assert not hasattr(telemetry, "simulate_llm") and not hasattr(telemetry, "simulate_diffusion")


def test_live_llm_records_measured_usage_and_ttft(live, trend):
    run = _wait(live, approve(live, trend), lambda r: (r.get("quoteRound") or {}).get("status") == "awaiting")
    steps = {st["key"]: st for st in run["steps"]}
    assert run["techPack"]["garmentName"] == "Fake Test Jacket"
    calls = steps["techpack"]["telemetry"]
    assert calls and calls[0]["ok"] and calls[0]["fake"] is True and "mode" not in calls[0]
    c = calls[0]
    assert c["model"] == "fake/llm-model"  # auto-discovered from /v1/models
    assert c["endpointHost"] == VLLM and c["gpu"] == "FAKE-GPU-LABEL"
    assert c["completionTokens"] > 0 and c["promptTokens"] > 0 and c["ttftMs"] is not None
    assert c["tokensPerSec"] > 0
    assert any(line.startswith("Inference: ") for line in steps["techpack"]["log"])
    assert not any("Llama" in line for line in steps["techpack"]["log"])  # no hardcoded model claims
    # RFQ drafting was live too, and recorded on the outreach step
    assert any(c["purpose"] == "rfq_emails" for c in steps["supplier_outreach"]["telemetry"])
    assert any("FAKE upstream" in line for line in steps["techpack"]["log"])  # the log says it was a fake


def test_live_llm_without_gpu_label_reports_none(s, monkeypatch):
    go_live(monkeypatch, s, amd_gpu_label="")
    route()
    client = openai_compat.make_client(s.amd_vllm_endpoint, "k1", 5)
    out = asyncio.run(openai_compat.chat_json(client, "m", lambda a: [{"role": "user", "content": "hi"}],
                                              lambda d: d, purpose="ping"))
    assert out["ok"] is True
    call = telemetry.snapshot().calls[0]
    assert call.gpu is None  # never invented


def test_non_streaming_mode_still_records_usage(s, monkeypatch):
    go_live(monkeypatch, s, atelier_llm_stream=False)
    route()
    client = openai_compat.make_client(s.amd_vllm_endpoint, "k1", 5)
    asyncio.run(openai_compat.chat_json(client, "m", lambda a: [{"role": "user", "content": "hi"}], lambda d: d))
    call = telemetry.snapshot().calls[0]
    assert call.completion_tokens and call.tokens_per_sec


def test_live_vision_and_diffusion_telemetry(live):
    client = live
    r = client.post("/api/trends/analyze", json={"imageUrls": ["https://example.test/a.jpg"]})
    assert r.status_code == 200 and r.json()["trendName"] == "Fake Indigo Utility"
    trend = r.json()
    d = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 2}).json()["designs"]
    assert all(x["imageUrl"].endswith(".png") for x in d)
    t = client.get("/api/telemetry").json()
    diff = [c for c in t["calls"] if c["service"] == "diffusion"]
    assert len(diff) == 2 and all(c["serverMs"] == 12.5 and c["fake"] for c in diff)
    assert diff[0]["imagesPerSec"] == 80.0 and diff[0]["model"] == "fake/diffusion-model"
    vis = [c for c in t["calls"] if c["service"] == "vision"]
    assert vis and vis[0]["images"] == 1 and vis[0]["model"] == "fake/vlm-model"


# --------------------------------------------------------------------------- honest errors


def test_diffusion_errors_are_errors(client, s, monkeypatch):
    go_live(monkeypatch, s, atelier_diffusion_timeout=1.0)
    route(**{DIFF: create_openai_app()})  # wrong server on the diffusion port -> 404 on /generate
    trend = client.post("/api/trends/analyze", json={"imageUrls": ["https://example.test/a.jpg"]}).json()
    r = client.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1})
    assert r.status_code == 503 and r.json()["service"] == "diffusion" and "404" in r.json()["detail"]
    calls = client.get("/api/telemetry?service=diffusion").json()["calls"]
    assert len(calls) == 1 and calls[0]["ok"] is False and "404" in calls[0]["error"]


def test_unreachable_vllm_is_a_step_error(client, s, monkeypatch):
    go_live(monkeypatch, s, atelier_llm_timeout=1.0)
    route()
    trend = client.post("/api/trends/analyze", json={"imageUrls": ["https://example.test/a.jpg"]}).json()
    monkeypatch.setattr(s, "amd_vllm_endpoint", "http://nobody.fake:9/v1")  # not routed -> ConnectError
    run = _wait(client, approve(client, trend))
    tp = run["steps"][0]
    assert run["status"] == "failed" and tp["status"] == "error" and tp["service"] == "brain"
    assert "direct vLLM" in tp["error"] and tp["retryable"]


# --------------------------------------------------------------------------- Evolus adapter


def test_evolus_execute_polls_until_completed(s, monkeypatch):
    go_live(monkeypatch, s)
    app = create_evolus_app(polls_until_done=3)
    route(evolus_app=app)
    seen = []

    async def on_status(status, polls):
        seen.append(status)

    res = asyncio.run(evolus.execute_workflow("wf_out", {"tech_pack": {"a": 1}, "rfq_emails": [{"x": 1}],
                                                         "production_quantity": 300},
                                              purpose="supplier_outreach", on_status=on_status))
    assert res["status"] == "Completed" and res["polls"] == 3 and not res["timedOut"]
    assert seen == ["Running", "Completed"]
    ex = app.state.executions[res["executionId"]]
    assert ex["parameters"]["production_quantity"] == "300"  # Evolus parameters are strings (verified live)
    assert json.loads(ex["parameters"]["tech_pack"]) == {"a": 1}  # nested -> JSON string (flat object)
    assert "Atelier pipeline request" in ex["input"]
    assert evolus.outreach_status(res) == "sent"  # parsed from the JSON-string output
    call = telemetry.snapshot().calls[0]
    assert call.service == "evolus" and "Completed" in call.detail and call.gpu is None


def test_evolus_failed_execution_and_http_errors(s, monkeypatch):
    go_live(monkeypatch, s)
    route(evolus_app=create_evolus_app(fail=True))
    with pytest.raises(evolus.EvolusError, match="failed: step 2"):
        asyncio.run(evolus.execute_workflow("wf_out", {"a": 1}))
    with pytest.raises(evolus.EvolusError, match="409.*switched off"):
        asyncio.run(evolus.execute_workflow("wf_off", {"a": 1}))
    monkeypatch.setattr(s, "evolus_api_key", "wrong")
    with pytest.raises(evolus.EvolusError, match="401"):
        asyncio.run(evolus.execute_workflow("wf_out", {"a": 1}))
    assert all(not c.ok for c in telemetry.snapshot().calls)


def test_evolus_retries_without_parameters_and_times_out_politely(s, monkeypatch):
    go_live(monkeypatch, s)
    app = create_evolus_app(reject_parameters=True, polls_until_done=10_000)
    route(evolus_app=app)
    monkeypatch.setattr(s, "evolus_poll_timeout", 0.05)
    monkeypatch.setattr(s, "evolus_poll_interval", 0.01)
    res = asyncio.run(evolus.execute_workflow("wf_out", {"a": 1}))
    assert res["timedOut"] is True and res["status"] == "Running"
    assert app.state.executions[res["executionId"]]["parameters"] == {}  # second attempt: input only
    assert evolus.outreach_status(res) == "queued"


def test_evolus_paths_are_configurable(s, monkeypatch):
    go_live(monkeypatch, s, evolus_execute_path="/custom/{workflow_id}/run")
    route()
    with pytest.raises(evolus.EvolusError, match="404"):
        asyncio.run(evolus.execute_workflow("wf_out", {"a": 1}))


def test_outreach_status_on_the_real_workflow_output():
    """The execution record of "Atelier - send RFQ emails" (scripts/provision_evolus_workflows.py), as polled live:
    `output` is the Summary script's JSON as a string. Only emailStatus "sent" marks the RFQs sent."""
    def run(status: str, results: list[str]) -> dict:
        out = {"emailStatus": status, "sentCount": results.count("handed to the Evolus mailer"), "kind": "rfq",
               "emails": [{"toEmail": f"m{i}@mill.example", "result": r, "error": None} for i, r in enumerate(results)]}
        return {"executionId": "e1", "status": "Completed", "execution": {"status": "Completed",
                                                                         "output": json.dumps(out)}}

    assert evolus.outreach_status(run("sent", ["handed to the Evolus mailer"] * 2)) == "sent"
    # one address had no email step in the workflow: not every RFQ went out -> "queued", never "sent"
    assert evolus.outreach_status(run("partial", ["handed to the Evolus mailer", "not sent"])) == "queued"


def test_evolus_shape_helpers():
    # Evolus execution parameters are all strings (a number gets HTTP 400 "… must be a string", verified live)
    assert evolus._flatten({"a": {"b": 1}, "c": [1], "d": 2, "e": None, "f": 42.5, "g": True, "h": "x"}) == {
        "a": '{"b": 1}', "c": "[1]", "d": "2", "f": "42.5", "g": "true", "h": "x"}
    assert evolus.parse_shopify({"execution": {"output": json.dumps({"product": {"id": "gid://x/1",
                                                                                 "url": "https://s/products/h"}})}}
                                ) == {"productId": "gid://x/1", "url": "https://s/products/h", "handle": "h"}


# --------------------------------------------------------------------------- health


def test_health_probes_live_endpoints(client, s, monkeypatch):
    go_live(monkeypatch, s, evolus_agent_model="app_test:agent_sourcing", evolus_extractor_agent_id="agent_x",
            evolus_extractor_id="ext_quote", evolus_shopify_workflow_id="wf_shop")  # v3 services
    route(shopify_app=create_shopify_app())
    body = client.get("/api/health").json()
    services = {x["name"]: x for x in body["services"]}
    assert all(x["status"] == "connected" and x["healthy"] and x["fake"] for x in services.values()), services
    assert services["llm"]["model"] == "fake/llm-model" and "latencyMs" in services["llm"]
    assert services["diffusion"]["gpu"] == "FAKE-GPU-LABEL"
    assert body["poweredBy"] == {"amd": False, "evolus": False, "modelConnected": False} and body["fakeUpstreams"]
    assert "FAKE-GPU" in services["diffusion"]["detail"]
    assert "authenticated" in services["evolus_outreach"]["detail"]
    assert "Fake Atelier Dev Store" in services["shopify"]["detail"]


def test_health_reports_unhealthy_and_caches(client, s, monkeypatch):
    go_live(monkeypatch, s, atelier_health_cache_seconds=60)
    hits = {"n": 0}
    llm_app = create_openai_app(api_key="other-key")

    @llm_app.middleware("http")
    async def count(request, call_next):
        hits["n"] += 1
        return await call_next(request)

    route(**{VLLM: llm_app})
    monkeypatch.setattr(s, "evolus_api_key", "wrong")
    services = {x["name"]: x for x in client.get("/api/health").json()["services"]}
    assert services["llm"]["status"] == "unreachable" and "401" in services["llm"]["detail"]
    assert services["llm"]["hint"] and services["evolus_outreach"]["status"] == "unreachable"
    client.get("/api/health")
    assert hits["n"] == 1  # cached

    probe.clear_cache()
    monkeypatch.setattr(s, "amd_vllm_endpoint", "http://nobody.fake:9/v1")
    services = {x["name"]: x for x in client.get("/api/health").json()["services"]}
    assert not services["llm"]["healthy"] and "unreachable" in services["llm"]["detail"]
