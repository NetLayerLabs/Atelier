"""Test setup (v5: there is no mock mode).

* `client`   - the app with NO service configured: every model / Evolus / Shopify call must fail honestly.
* `fakes`    - configures every service against the in-process TEST DOUBLES in tests/fake_upstreams.py (routed with
               RoutingTransport, no sockets). They are test doubles, not app data; health reports them as fake.
* `trend`    - a trend analysed by the fake VLM from an uploaded image (needs `fakes`).
"""

import os
import sys
import tempfile
from pathlib import Path

# Must be set before the app (and its cached settings) is imported: nothing from backend/.env may leak in.
_SERVICE_VARS = (
    "AMD_VLLM_ENDPOINT", "AMD_VLLM_MODEL", "AMD_VLLM_API_KEY", "AMD_VISION_ENDPOINT", "AMD_VISION_MODEL",
    "AMD_DIFFUSION_ENDPOINT", "AMD_DIFFUSION_API_KEY", "AMD_GPU_LABEL", "EVOLUS_API_KEY", "EVOLUS_WORKSPACE_ID",
    "EVOLUS_OUTREACH_WORKFLOW_ID", "EVOLUS_SHOPIFY_WORKFLOW_ID", "EVOLUS_PO_WORKFLOW_ID", "EVOLUS_AGENT_MODEL",
    "EVOLUS_LIBRARY_ID", "EVOLUS_EXTRACTOR_ID", "EVOLUS_EXTRACTOR_AGENT_ID", "EVOLUS_NEGOTIATION_WORKFLOW_ID",
    "EVOLUS_INBOUND_WORKFLOW_ID", "EVOLUS_WEBHOOK_SECRET", "EVOLUS_USER_API_KEY", "SUPPLIER_INBOX",
    "SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_TOKEN", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
    "SHOPIFY_WEBHOOK_SECRET", "SHOPIFY_STOREFRONT_PASSWORD", "SHOPIFY_SHORT_URL", "AMD_TOKEN_FACTORY_KEY",
    "EVOLUS_AGENT_LABEL", "EVOLUS_OWN_MODEL_NAME")
for _k in _SERVICE_VARS:
    os.environ[_k] = ""
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["EVOLUS_AGENT_BACKEND"] = "AMD vLLM"  # the doubles stand in for our own vLLM
os.environ["DEMAND_STAGE_THRESHOLD"] = "0"
os.environ["ATELIER_DATA_DIR"] = tempfile.mkdtemp(prefix="atelier-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import fx, http, openai_compat, probe, telemetry  # noqa: E402
from app.store import store  # noqa: E402
from fake_upstreams import (RoutingTransport, create_diffusion_app, create_ecb_app,  # noqa: E402
                            create_evolus_app, create_openai_app, create_shopify_app, tiny_png)

VLLM = "vllm.fake:8000"
VLM = "vlm.fake:8001"
DIFF = "diffusion.fake:8002"
EVO = "evolus.fake"
SHOP = "shop.fake"
ECB = "ecb.fake"


def _reset() -> None:
    store.clear()
    telemetry.clear()
    telemetry.FAKE_HOSTS.clear()
    probe.clear_cache()
    fx.clear_cache()
    openai_compat._model_cache.clear()
    http.set_transport(None)


@pytest.fixture(autouse=True)
def fake_vision(request, monkeypatch):
    """Canned vision answers (tests/vision_double.py) unless the test is marked `real_vision` or a test has
    pointed the app at a (fake) live vision endpoint, in which case the real vision service runs."""
    if request.node.get_closest_marker("real_vision"):
        yield None
        return
    from . import vision_double

    from app.config import get_settings
    from app.routers import trends
    from app.services import vision

    real = vision.analyze_images

    async def analyze(images):
        if get_settings().vision_live:
            return await real(images)
        return await vision_double.fake_analyze_images(images)

    vision_double.calls.clear()
    monkeypatch.setattr(vision, "analyze_images", analyze)
    monkeypatch.setattr(trends, "_vision_ready", lambda: True)
    yield vision_double


@pytest.fixture(autouse=True)
def test_workspace(tmp_path, monkeypatch):
    """v5: every test gets its own Brand workspace in a temp dir, seeded with clearly synthetic TEST data
    (tests/workspace_fixture.py). Tests that need an empty workspace call workspace.wipe()."""
    from app.config import get_settings

    from .workspace_fixture import seed

    monkeypatch.setattr(get_settings(), "atelier_data_dir", str(tmp_path / "atelier-data"))
    seed()
    yield


@pytest.fixture
def s(tmp_path, monkeypatch):
    st = config.get_settings()  # the data dir (workspace + sequences) is the per-test one from `test_workspace`
    monkeypatch.setattr(st, "evolus_poll_interval", 0.0)
    monkeypatch.setattr(st, "shopify_poll_interval", 0.01)
    _reset()
    yield st
    _reset()


@pytest.fixture
def client(s):
    # QA H5: without ATELIER_ADMIN_TOKEN only this machine may change state, so the test client is a loopback client.
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


def go_live(monkeypatch, st, **over):
    """Point every service at the fakes (the brain = direct vLLM unless EVOLUS_AGENT_MODEL is set in `over`)."""
    vals = {
        "amd_vllm_endpoint": f"http://{VLLM}/v1", "amd_vllm_api_key": "k1", "amd_vllm_model": "",
        "amd_vision_endpoint": f"http://{VLM}/v1",
        "amd_diffusion_endpoint": f"http://{DIFF}/generate",
        "amd_gpu_label": "FAKE-GPU-LABEL",
        "evolus_api_base": f"http://{EVO}", "evolus_api_key": "test-key", "evolus_workspace_id": "app_test",
        "evolus_outreach_workflow_id": "wf_out", "evolus_shopify_workflow_id": "", "evolus_po_workflow_id": "wf_po",
        "shopify_store_domain": f"http://{SHOP}", "shopify_admin_token": "shpat_fake",
        "atelier_fx_url": f"http://{ECB}/stats/eurofxref/eurofxref-daily.xml",
    }
    vals.update(over)
    for k, v in vals.items():
        monkeypatch.setattr(st, k, v)


IMAGE_HOST_IP = "93.184.215.14"  # what the test resolver returns for image URLs (routed to `image_app` below)


def image_app():
    """TEST DOUBLE for a public image host (QA M6: the backend fetches image URLs itself)."""
    from fastapi import FastAPI
    from fastapi.responses import Response

    app = FastAPI()

    @app.get("/{path:path}")
    async def img(path: str) -> Response:
        return Response(tiny_png(), media_type="image/png")

    return app


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """No real DNS in tests: every image host resolves to IMAGE_HOST_IP (a public address), except names a test
    maps itself via `fake_dns[name] = [addresses]`."""
    from app.services import safe_fetch

    table: dict[str, list[str]] = {}

    async def resolve(host: str, port: int) -> list[str]:
        return table.get(host, [IMAGE_HOST_IP])

    monkeypatch.setattr(safe_fetch, "resolve", resolve)
    return table


def route(evolus_app=None, shopify_app=None, **extra):
    routes = {
        IMAGE_HOST_IP: image_app(),
        VLLM: create_openai_app(api_key="k1", model="fake/llm-model"),
        VLM: create_openai_app(api_key="k1", model="fake/vlm-model"),
        DIFF: create_diffusion_app(model="fake/diffusion-model"),
        EVO: evolus_app or create_evolus_app(),
        SHOP: shopify_app or create_shopify_app(),
        ECB: create_ecb_app(),
    }
    routes.update(extra)
    http.set_transport(RoutingTransport(routes))
    return routes


@pytest.fixture
def fakes(s, monkeypatch):
    go_live(monkeypatch, s)
    return route()


@pytest.fixture
def live(client, fakes):
    """A client with every service connected to the test doubles."""
    return client


@pytest.fixture
def trend(live):
    r = live.post("/api/trends/analyze", files=[("images", ("board.png", tiny_png(), "image/png"))])
    assert r.status_code == 200, r.text
    return r.json()
