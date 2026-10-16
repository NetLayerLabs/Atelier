"""v2 creative direction + collections (v5: the brain interprets, the diffusion server renders; no keyword
interpreter and no fixed cm / cost effects). Model traffic goes to the in-process test doubles."""

import json

import pytest
from helpers import design, wait

from app.services import direction as direction_svc

DIRECTION_KEYS = {"id", "designId", "instruction", "interpretation", "promptAdditions", "promptRemovals",
                  "silhouetteChanges", "techPackHints", "references", "createdAt"}
FAKE_AFTER = ["#101418", "#3A3F47", "#8A8F96"]  # what the fake model returns as paletteAfter


def _awaiting(r):
    return (r.get("quoteRound") or {}).get("status") == "awaiting" or r["status"] != "running"


def test_direct_endpoint_and_lineage(live, trend):
    parent = design(live, trend)
    r = live.post(f"/api/designs/{parent['id']}/direct", json={"instruction": "make it darker, cropped, more Margiela"})
    assert r.status_code == 200, r.text
    body = r.json()
    d = body["direction"]
    assert DIRECTION_KEYS <= set(d) and d["id"].startswith("dir_") and d["designId"] == parent["id"]
    assert "mode" not in d and d["generatedBy"] == "direct vLLM"
    assert d["interpretation"].startswith("I'll deepen") and d["techPackHints"] == ["Shorten body length 4cm"]
    assert d["paletteShift"]["after"] == FAKE_AFTER and d["paletteShift"]["before"] == trend["colorPalette"]
    assert len(body["designs"]) == 4
    for k in body["designs"]:
        assert k["parentDesignId"] == parent["id"] and k["directionId"] == d["id"]
        assert k["vibe"] == "make it darker, cropped, more Margiela" and k["imageUrl"].endswith(".png")
        assert "deeper palette" in k["prompt"] and FAKE_AFTER[0] in k["prompt"]
    assert live.get(f"/api/directions/{d['id']}").json() == d
    kid = body["designs"][0]
    r2 = live.post(f"/api/designs/{kid['id']}/direct", json={"instruction": "longer", "count": 1}).json()
    st = direction_svc.state_for(r2["designs"][0]["id"])
    assert len(st.direction_ids) == 2 and st.palette == FAKE_AFTER
    assert not hasattr(st, "length_cm") and not hasattr(direction_svc, "interpret_mock")


def test_direct_without_a_brain_is_503_and_makes_nothing(live, trend, s, monkeypatch):
    parent = design(live, trend)
    monkeypatch.setattr(s, "amd_vllm_endpoint", "")
    r = live.post(f"/api/designs/{parent['id']}/direct", json={"instruction": "darker"})
    assert r.status_code == 503 and r.json()["service"] == "brain" and r.json()["status"] == "not_configured"
    from app.store import store

    assert store.directions == {} and all(x.parent_design_id is None for x in store.designs.values())


def test_direct_then_approve_techpack_brief_carries_the_hints(live, trend, fakes):
    parent = design(live, trend)
    body = live.post(f"/api/designs/{parent['id']}/direct",
                     json={"instruction": "make it darker, cropped", "count": 1}).json()
    kid = body["designs"][0]
    run = wait(live, approve_design(live, kid), _awaiting)
    tp = run["techPack"]
    assert tp["colorway"] == FAKE_AFTER  # the factory makes what was directed
    assert run["steps"][0]["route"] == "direct vLLM"
    brief = direction_svc.techpack_brief(direction_svc.store.designs[kid["id"]])
    assert brief["techPackHints"] == ["Shorten body length 4cm"] and brief["palette"] == FAKE_AFTER


def approve_design(client, d):
    r = client.post(f"/api/designs/{d['id']}/approve", json={"productionQuantity": 300})
    assert r.status_code == 200, r.text
    return r.json()["runId"]


def test_direct_errors(live, trend):
    assert live.post("/api/designs/dsn_missing/direct", json={"instruction": "darker"}).status_code == 404
    d = design(live, trend)
    for body in ({"instruction": "   "}, {}, {"instruction": "x" * 501}, {"instruction": "darker", "count": 9}):
        r = live.post(f"/api/designs/{d['id']}/direct", json=body)
        assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert live.get("/api/directions/dir_nope").status_code == 404


def test_refine_still_works_alongside_direct(live, trend):
    d = design(live, trend)
    kid = live.post(f"/api/designs/{d['id']}/direct", json={"instruction": "darker", "count": 1}).json()["designs"][0]
    r = live.post(f"/api/designs/{kid['id']}/refine", json={"vibe": "softer", "count": 2})
    assert r.status_code == 200 and all(x["parentDesignId"] == kid["id"] for x in r.json()["designs"])


# --------------------------------------------------------------------------- collections


def test_collection_is_planned_by_the_brain(live, trend):
    r = live.post("/api/collections/generate", json={"trendId": trend["id"], "size": 4})
    assert r.status_code == 200, r.text
    col = r.json()
    assert col["id"].startswith("col_") and col["name"] == "Fake Capsule" and col["generatedBy"] == "direct vLLM"
    assert "mode" not in col and len(col["designs"]) == 4 and len(col["looks"]) == 4
    assert col["designs"][0]["garmentType"] == trend["garmentType"]
    assert [d["garmentType"] for d in col["designs"][1:]] == ["wide-leg trousers", "ribbed knit top", "longline coat"]
    for i, (d, look) in enumerate(zip(col["designs"], col["looks"])):
        assert d["collectionId"] == col["id"] and look["designId"] == d["id"]
        assert look["caption"] == f"Canned look {i + 1} (fake model)"
    assert live.get(f"/api/collections/{col['id']}").json() == col
    piece = col["designs"][1]
    kid = live.post(f"/api/designs/{piece['id']}/direct", json={"instruction": "cropped", "count": 1}).json()["designs"][0]
    assert kid["collectionId"] == col["id"] and kid["garmentType"] == piece["garmentType"]


def test_collection_uses_the_brain_chain_not_only_vllm(client, s, monkeypatch):
    """The planner goes through the brain chain: with only the Evolus agent configured it still works."""
    from conftest import go_live, route

    go_live(monkeypatch, s, evolus_agent_model="app_test:agent_sourcing")
    apps = route()
    t = client.post("/api/trends/analyze", json={"imageUrls": ["https://example.test/a.jpg"]}).json()
    monkeypatch.setattr(s, "amd_vllm_endpoint", "")  # no direct vLLM: the Evolus agent is the only brain
    col = client.post("/api/collections/generate", json={"trendId": t["id"], "size": 3}).json()
    assert col["generatedBy"] == "evolus-agent → AMD vLLM" and len(col["designs"]) == 3
    assert any("Plan a coherent" in json.dumps(c) for c in apps["evolus.fake"].state.chat_calls)


def test_collection_without_a_brain_is_503(live, trend, s, monkeypatch):
    monkeypatch.setattr(s, "amd_vllm_endpoint", "")
    r = live.post("/api/collections/generate", json={"trendId": trend["id"], "size": 3})
    assert r.status_code == 503 and r.json()["service"] == "brain"


def test_collection_errors(live, trend):
    assert live.post("/api/collections/generate", json={"trendId": "trd_nope"}).status_code == 404
    for size in (2, 6):
        assert live.post("/api/collections/generate", json={"trendId": trend["id"], "size": size}).status_code == 422
    assert live.get("/api/collections/col_nope").status_code == 404


@pytest.mark.parametrize("bad", [{"interpretation": ""}, {"nope": 1}])
def test_invalid_brain_output_is_retried_then_an_error(live, trend, monkeypatch, bad):
    import fake_upstreams as fake

    real = fake._reply_for
    monkeypatch.setattr(fake, "_reply_for",
                        lambda m: json.dumps(bad) if "creative director says" in json.dumps(m).lower() else real(m))
    d = design(live, trend)
    r = live.post(f"/api/designs/{d['id']}/direct", json={"instruction": "darker", "count": 1})
    assert r.status_code == 503 and r.json()["service"] == "brain"
    calls = [c for c in live.get("/api/telemetry?service=llm").json()["calls"] if c["purpose"] == "creative_direction"]
    assert [c["attempt"] for c in calls] == [2, 1] and not any(c["ok"] for c in calls)  # one retry, then honest
