"""
Black-box smoke tests against a deployed Sanjabai instance.

No source checkout or database access needed -- everything here is a plain
HTTP request against BACKEND_URL / FRONTEND_URL. Tolerant of a few possible
status codes where the "correct" one is a judgment call (e.g. a public
listing endpoint returning 200 with an empty list vs 404 when nothing is
configured yet) -- the point is "is this deployment fundamentally alive and
answering", not exact-shape contract testing (that's what backend/tests/
already does against mocks).
"""
import os

import pytest
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3003").rstrip("/")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"} if AUTH_TOKEN else {}

TIMEOUT = 15


def _get(base, path, **kw):
    kw.setdefault("timeout", TIMEOUT)
    return requests.get(f"{base}{path}", **kw)


# ── Backend health ──────────────────────────────────────────────

def test_health():
    r = _get(BACKEND, "/health")
    assert r.status_code == 200, f"/health -> {r.status_code}"


def test_health_detailed_or_absent():
    # Not every deployment exposes /health/detailed publicly (this one gates
    # it behind auth); tolerate 401 as well as a plain 404.
    assert _get(BACKEND, "/health/detailed").status_code in (200, 401, 404)


# ── Public catalog / content endpoints ──────────────────────────

def test_model_catalog():
    r = _get(BACKEND, "/catalog/models")
    assert r.status_code == 200
    assert isinstance(r.json(), (list, dict))


def test_exchange_rate():
    # This endpoint tries a live upstream fetch (tgju.org, then a fallback
    # API) before falling back to a hardcoded constant -- on a cold cache it
    # can take several seconds even when everything is healthy, so it gets
    # a longer timeout than the rest of this file's quick checks.
    r = _get(BACKEND, "/exchange-rate", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "usd_to_irt" in data
    assert "eur_to_irt" in data


def test_hermes_offerings_public():
    """Catalog is meant to be browsable without auth (see the /hermes
    PUBLIC_ROUTES fix) -- must never require a session."""
    r = _get(BACKEND, "/hermes/offerings")
    assert r.status_code == 200, f"/hermes/offerings -> {r.status_code} (should be public)"
    offerings = r.json()
    assert isinstance(offerings, list)
    for o in offerings:
        # Server-authoritative pricing: Toman fields must be present and
        # integer; no EUR figure should ever reach a public response.
        assert "monthly_price_irt" in o
        assert isinstance(o["monthly_price_irt"], int)
        assert "provider_cost_eur" not in o
        assert "eur_to_irt" not in o


def test_hermes_skill_catalog_public():
    r = _get(BACKEND, "/hermes/skill-catalog")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Auth-gated endpoints reachable + correctly gated ─────────────

def test_admin_unauthenticated():
    # 429 is also acceptable here: the admin rate limiter is shared across
    # every admin-path check in this suite (and across repeated runs within
    # its window), so a rate-limited caller still correctly got no admin
    # data back -- see security_test.py for the dedicated 401-vs-429
    # distinction with a fresh budget.
    assert _get(BACKEND, "/admin/pricing").status_code in (401, 403, 429)


def test_admin_hermes_orders_unauthenticated():
    assert _get(BACKEND, "/admin/hermes/orders").status_code in (401, 403, 429)


@pytest.mark.skipif(not AUTH_TOKEN, reason="AUTH_TOKEN not set")
class TestAuthed:
    def test_wallet(self):
        assert _get(BACKEND, "/wallet", headers=AUTH_HEADERS).status_code == 200

    def test_hermes_orders(self):
        assert _get(BACKEND, "/hermes/orders", headers=AUTH_HEADERS).status_code == 200

    def test_hermes_servers(self):
        assert _get(BACKEND, "/hermes/servers", headers=AUTH_HEADERS).status_code == 200

    def test_list_skills(self):
        assert _get(BACKEND, "/skills", headers=AUTH_HEADERS).status_code == 200

    def test_list_assistants(self):
        assert _get(BACKEND, "/assistants", headers=AUTH_HEADERS).status_code == 200


# ── Frontend routes ──────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/chat", "/models", "/pricing", "/hermes", "/admin"])
def test_frontend_route_200(path):
    r = requests.get(f"{FRONTEND}{path}", timeout=TIMEOUT)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
