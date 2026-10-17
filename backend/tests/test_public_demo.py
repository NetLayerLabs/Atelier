"""Hosted demo (ATELIER_ADMIN_TOKEN set): visitors without the token can try every step that has no outside effect;
approving (real supplier emails, a real Shopify product) and the Brand workspace stay behind the token. Model calls are
rate-limited per visitor and in total, and visitors never see a real email address in our JSON."""

from __future__ import annotations

import pytest
from fake_upstreams import tiny_png
from fastapi.testclient import TestClient

from app import security
from app.main import app

TOKEN = "qa-admin-token-123"
VISITOR = ("203.0.113.9", 4000)


@pytest.fixture
def hosted(s, fakes, monkeypatch):
    """Every service connected to the test doubles, and the admin token set (the hosted deployment)."""
    monkeypatch.setattr(s, "atelier_admin_token", TOKEN)
    security.limiter.reset()
    yield s
    security.limiter.reset()


def _trend(c) -> dict:
    r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))])
    assert r.status_code == 200, r.text
    return r.json()


def test_a_visitor_can_try_the_safe_steps_but_not_approve(hosted):
    with TestClient(app, client=VISITOR) as c:
        trend = _trend(c)  # read a mood board
        d = c.post("/api/designs/generate", json={"trendId": trend["id"], "count": 1})
        assert d.status_code == 200, d.text  # concepts
        design = d.json()["designs"][0]
        sketch = c.post("/api/designs/upload", data={"trendId": trend["id"]},
                        files={"file": ("s.png", tiny_png(), "image/png")})
        assert sketch.status_code not in (401, 403, 429)  # allowed through (the vision double decides the rest)
        # Approve emails real suppliers and creates a real Shopify product: the token only. So do the steps after it,
        # and the two review findings of 17 Oct: the forecast (heavy maths, not rate-limited) and applying customer
        # voice (it changes a design an admin may approve).
        assert c.post("/api/forecast", json={}).status_code == 401
        assert c.post("/api/voice/voc_x/apply", json={"designId": design["id"]}).status_code == 401
        r = c.post(f"/api/designs/{design['id']}/approve", json={"productionQuantity": 300})
        assert r.status_code == 401 and r.json()["auth"] == "required" and "Visitors can try" in r.json()["detail"]
        for path in ("/api/guardrails/review", "/api/workspace/suppliers/confirm", "/api/runs/run_x/retry",
                     "/api/designs/upload/../approve", "/api/trends/analyze/"):
            assert c.post(path, json={"confirm": True}).status_code == 401, path
        assert c.put("/api/workspace/profile", json={"name": "x", "currency": "EUR"}).status_code == 401
        assert c.delete("/api/workspace?confirm=DELETE").status_code == 401
        # With the token everything works as before.
        ok = c.post(f"/api/designs/{design['id']}/approve", json={"productionQuantity": 300},
                    headers={"Authorization": f"Bearer {TOKEN}"})
        assert ok.status_code == 200, ok.text


def test_other_sites_still_cannot_use_the_public_steps(hosted):
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))],
                   headers={"Origin": "https://evil.example"})
        assert r.status_code == 403 and "cross-origin" in r.json()["detail"]


def test_public_demo_can_be_switched_off(hosted, monkeypatch):
    monkeypatch.setattr(hosted, "atelier_public_demo", False)
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))])
        assert r.status_code == 401


def test_without_a_token_the_local_only_rule_is_unchanged(s, fakes):
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))])
        assert r.status_code == 403 and "ATELIER_ADMIN_TOKEN" in r.json()["detail"]


def test_model_calls_are_rate_limited_per_visitor_and_in_total(hosted, monkeypatch):
    monkeypatch.setattr(hosted, "atelier_public_rate_per_visitor", 2)
    monkeypatch.setattr(hosted, "atelier_public_rate_total", 3)
    with TestClient(app, client=VISITOR) as c:
        _trend(c)
        _trend(c)
        r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))])
        assert r.status_code == 429 and r.json()["auth"] == "rate_limited" and "Demo limit" in r.json()["detail"]
        # A forged X-Real-IP from a public peer is ignored (still this visitor).
        r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))],
                   headers={"X-Real-IP": "198.51.100.77"})
        assert r.status_code == 429
        ok = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))],
                    headers={"Authorization": f"Bearer {TOKEN}"})
        assert ok.status_code == 200  # signed in: no demo limit
    # Behind the local reverse proxy, X-Real-IP is the visitor: another visitor has their own allowance...
    with TestClient(app, client=("172.18.0.1", 4000)) as proxy:
        r = proxy.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))],
                       headers={"X-Real-IP": "198.51.100.8"})
        assert r.status_code == 200, r.text
        # ...until the total for everyone is reached (3 here: 2 + 1).
        r = proxy.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))],
                       headers={"X-Real-IP": "198.51.100.9"})
        assert r.status_code == 429 and "busy" in r.json()["detail"]


def test_the_rate_window_slides():
    lim = security.RateLimiter()
    assert lim.hit("a", 1, 0, now=1000.0) is None
    assert lim.hit("a", 1, 0, now=1001.0) is not None  # refused, and not counted
    assert lim.hit("a", 1, 0, now=1000.0 + security.RATE_WINDOW + 1) is None


def test_visitors_never_see_a_real_email_address(hosted):
    with TestClient(app, client=VISITOR) as c:
        sup = c.get("/api/workspace/suppliers")
        assert sup.status_code == 200
        text = sup.text
        assert "@supplier.test" in text and "•••@supplier.test" in text
        assert all(e.split("@")[0].endswith("•••") for x in sup.json() for e in x["emails"])
        assert int(sup.headers["content-length"]) == len(sup.content)
        admin = c.get("/api/workspace/suppliers", headers={"Authorization": f"Bearer {TOKEN}"})
        assert "•••" not in admin.text and all("•••" not in e for x in admin.json() for e in x["emails"])
    with TestClient(app, client=("127.0.0.1", 4000)) as local:  # this machine, signed out: still masked
        assert "•••@supplier.test" in local.get("/api/workspace/suppliers").text


def test_no_token_no_masking(s):
    with TestClient(app, client=("127.0.0.1", 4000)) as local:
        text = local.get("/api/workspace/suppliers").text
        assert "@supplier.test" in text and "•••" not in text


def test_mask_emails_keeps_the_domain_only():
    out = security.mask_emails(b'{"to":"jane.doe@gmail.com","x":"a.b-c@sub.example.co.uk","y":"no email"}')
    assert out == '{"to":"j•••@gmail.com","x":"a•••@sub.example.co.uk","y":"no email"}'.encode()


def test_visitor_uploads_pause_when_the_uploads_folder_is_full(hosted, monkeypatch):
    """The uploads folder sits on a disk the host shares with other services: visitors can't fill it."""
    monkeypatch.setattr(hosted, "atelier_public_uploads_max_mb", 0)  # "full" right away
    security._uploads_size.clear()
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))])
        assert r.status_code == 503 and r.json()["auth"] == "paused" and "preset" in r.json()["detail"]
        trend = c.post("/api/trends/analyze", files=[("images", ("b.png", tiny_png(), "image/png"))],
                       headers={"Authorization": f"Bearer {TOKEN}"})
        assert trend.status_code == 200  # signed in: not limited
        r = c.post("/api/designs/upload", data={"trendId": trend.json()["id"]},
                   files={"file": ("s.png", tiny_png(), "image/png")})
        assert r.status_code == 503
    security._uploads_size.clear()


def test_customer_voice_csv_upload_stays_behind_the_token(hosted):
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/voice/upload", files={"file": ("r.csv", b"review_text\nnice\n", "text/csv")})
        assert r.status_code == 401


def test_a_masked_address_is_never_saved_over_the_real_one(hosted):
    """Review finding (17 Oct): the workspace page loaded signed out holds masked emails; saving them after signing
    in must not replace the real contact."""
    admin = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, client=VISITOR) as c:
        sup = c.get("/api/workspace/suppliers").json()[0]  # what a signed-out page holds
        assert "•••@" in sup["emails"][0]
        real = c.get("/api/workspace/suppliers", headers=admin).json()[0]["emails"][0]
        body = {k: sup[k] for k in ("name", "city", "country", "language", "emails", "categories", "capabilities")}
        r = c.put(f"/api/workspace/suppliers/{sup['id']}", json=body, headers=admin)
        assert r.status_code == 422 and "masked" in r.json()["detail"] and "reload" in r.json()["detail"]
        assert c.get("/api/workspace/suppliers", headers=admin).json()[0]["emails"][0] == real  # unchanged


def test_an_image_too_large_to_decode_is_refused_before_decoding(hosted):
    """Review finding (17 Oct): a small file that decodes to a huge image could exhaust memory."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("1", (8000, 6000)).save(buf, format="PNG")  # 48 megapixels, a few kB on disk
    bomb = buf.getvalue()
    assert len(bomb) < 200_000
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/trends/analyze", files=[("images", ("big.png", bomb, "image/png"))])
        assert r.status_code == 413 and "megapixels" in r.json()["detail"]
        trend = _trend(c)
        r = c.post("/api/designs/upload", data={"trendId": trend["id"]}, files={"file": ("big.png", bomb, "image/png")})
        assert r.status_code == 413


def test_a_huge_forecast_is_refused_before_it_allocates(s):
    """Review finding (17 Oct): priorMeanPreorders=250,000 took 1.5 GB in one request (the VPS container has 768 MB,
    and a restart wipes every run). Now the exact table is bounded and the request is refused at once."""
    import time

    body = {"launchAt": "2026-10-17T10:00:00Z", "asOf": "2026-10-17T10:00:00Z",
            "economics": {"unitCost": 20, "retailPrice": 60},
            "assumptions": {"priorMeanPreorders": 1_000_000, "seasonMultiplier": 50, "priorCv": 5}}
    with TestClient(app, client=("127.0.0.1", 4000)) as local:  # this machine, no token: allowed to call it
        t = time.perf_counter()
        r = local.post("/api/forecast", json=body)
        assert r.status_code == 422 and "outside what the forecast computes exactly" in r.json()["detail"]
        assert time.perf_counter() - t < 2.0
        ok = local.post("/api/forecast", json={**body, "assumptions": {}})
        assert ok.status_code == 200, ok.text  # the defaults still work


def test_an_image_pillow_refuses_to_open_counts_as_too_large(hosted):
    import io

    from PIL import Image

    from app.services import files

    buf = io.BytesIO()
    Image.new("1", (15000, 15000)).save(buf, format="PNG")  # 225 megapixels: above Pillow's own bomb limit
    assert files.too_many_pixels(buf.getvalue())
    with TestClient(app, client=VISITOR) as c:
        r = c.post("/api/trends/analyze", files=[("images", ("huge.png", buf.getvalue(), "image/png"))])
        assert r.status_code == 413


def test_a_huge_orders_list_is_refused_before_it_allocates(s):
    """Audit (17 Oct): 20,000 orders x 10,000 units each froze the local server (2 GB, swapping)."""
    import time

    orders = [{"timestamp": "2026-10-17T10:30:00Z", "quantity": 10_000} for _ in range(20_000)]
    body = {"launchAt": "2026-10-17T10:00:00Z", "asOf": "2026-10-17T12:00:00Z", "orders": orders,
            "economics": {"unitCost": 20, "retailPrice": 60}}
    with TestClient(app, client=("127.0.0.1", 4000)) as local:
        t = time.perf_counter()
        r = local.post("/api/forecast", json=body)
        assert r.status_code == 422 and "pre-order units" in r.json()["detail"]
        assert time.perf_counter() - t < 5.0
