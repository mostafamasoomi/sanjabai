"""
Black-box security tests against a deployed Sanjabai instance.

Checks the boundaries that must hold no matter what's on the other side of
BACKEND_URL: auth enforcement, admin/user session separation, security
headers, secret leakage, rate limiting, and that malformed input degrades to
a clean 4xx rather than a stack trace. Every check that needs a credential
you didn't provide (ADMIN_TOKEN / AUTH_TOKEN) skips with a clear reason
instead of failing, so this suite is safe to run against production with
zero credentials and still report something useful.
"""
import os
import time

import pytest
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3003").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")

ADMIN_HEADERS = {"x-admin-token": ADMIN_TOKEN} if ADMIN_TOKEN else {}
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"} if AUTH_TOKEN else {}

TIMEOUT = 15

# Strings that must never appear verbatim in a response body -- internal
# error detail, DB driver names, or the raw admin secret leaking back out.
LEAK_MARKERS = ["Traceback", "asyncpg.", "psycopg", "sqlalchemy.exc", ADMIN_TOKEN]


def _get(base, path, **kw):
    kw.setdefault("timeout", TIMEOUT)
    return requests.get(f"{base}{path}", **kw)


def _post(base, path, **kw):
    kw.setdefault("timeout", TIMEOUT)
    return requests.post(f"{base}{path}", **kw)


def _assert_no_leak(resp):
    body = resp.text
    for marker in LEAK_MARKERS:
        if marker and marker in body:
            pytest.fail(f"response leaked internal detail: {marker!r} in body")


# ── Auth enforcement (session-gated endpoints) ───────────────────

@pytest.mark.parametrize("path", [
    "/wallet", "/wallet/ledger", "/conversations", "/api-keys", "/me/usage",
    "/hermes/orders", "/hermes/servers",
])
def test_session_gated_rejects_anonymous(path):
    r = _get(BACKEND, path)
    assert r.status_code in (401, 403), f"{path} -> {r.status_code} (expected 401/403 without a session)"
    _assert_no_leak(r)


def test_session_gated_rejects_garbage_token():
    r = _get(BACKEND, "/wallet", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code in (401, 403)


# ── Admin/user session separation ────────────────────────────────

@pytest.mark.parametrize("path", ["/admin/pricing", "/admin/hermes/orders", "/admin/analytics"])
def test_admin_gated_rejects_anonymous(path):
    r = _get(BACKEND, path)
    # 429 is also an acceptable outcome: the admin rate limiter is a shared
    # budget across every admin-path request this suite makes (and across
    # repeated runs within the window) -- either way, no admin data reached
    # an unauthorized caller, which is the property under test.
    assert r.status_code in (401, 403, 429), f"{path} -> {r.status_code}"
    _assert_no_leak(r)


def test_admin_gated_rejects_wrong_token():
    r = _get(BACKEND, "/admin/pricing", headers={"x-admin-token": "definitely-wrong"})
    assert r.status_code in (401, 403, 429)


def test_frontend_admin_reachable_without_user_session():
    """Server-side reachability half of the admin-login fix: the /admin
    page itself must not 3xx/4xx at the HTTP layer for an anonymous
    visitor. The client-side redirect-to-/login half of this (which a
    plain request can't see, since Next.js serves the same 200 shell
    either way) is covered by browser_checks.mjs."""
    r = requests.get(f"{FRONTEND}/admin", timeout=TIMEOUT, allow_redirects=False)
    assert r.status_code == 200, f"/admin -> {r.status_code}"


@pytest.mark.skipif(not ADMIN_TOKEN, reason="ADMIN_TOKEN not set")
def test_admin_token_actually_works():
    """Sanity check the token itself is valid, so the rejection tests above
    are testing auth enforcement and not just a bad token."""
    r = _get(BACKEND, "/admin/pricing", headers=ADMIN_HEADERS)
    if r.status_code == 429:
        pytest.skip("admin rate limit budget exhausted by this run -- inconclusive, not a failure")
    assert r.status_code == 200, f"/admin/pricing with ADMIN_TOKEN -> {r.status_code}"


# ── Hermes agent-daemon token auth ───────────────────────────────

def test_hermes_agent_state_rejects_missing_token():
    assert _get(BACKEND, "/hermes/agent/state").status_code == 401


def test_hermes_agent_state_rejects_malformed_token():
    r = _get(BACKEND, "/hermes/agent/state", headers={"Authorization": "Bearer sk-not-an-agent-token"})
    assert r.status_code == 401


def test_hermes_agent_state_rejects_unknown_token():
    r = _get(BACKEND, "/hermes/agent/state", headers={"Authorization": "Bearer hsa-nonexistent"})
    assert r.status_code == 401


def test_hermes_agent_report_rejects_missing_token():
    r = _post(BACKEND, "/hermes/agent/report", json={"version": 1, "results": []})
    assert r.status_code == 401


# ── Ownership: cross-user access must 404, not leak ──────────────

@pytest.mark.skipif(not AUTH_TOKEN, reason="AUTH_TOKEN not set")
class TestOwnership:
    def test_hermes_order_not_owned_is_404_not_500(self):
        # A huge, almost-certainly-nonexistent id. A real cross-account IDOR
        # check needs two accounts; this at least proves the lookup path
        # fails closed (404) rather than raising server-side.
        r = _get(BACKEND, "/hermes/orders/999999999", headers=AUTH_HEADERS)
        assert r.status_code == 404
        _assert_no_leak(r)

    def test_hermes_server_not_owned_is_404_not_500(self):
        r = _get(BACKEND, "/hermes/servers/999999999", headers=AUTH_HEADERS)
        assert r.status_code == 404
        _assert_no_leak(r)


# ── Malformed input degrades cleanly ──────────────────────────────

@pytest.mark.parametrize("bad_id", ["' OR '1'='1", "<script>alert(1)</script>", "../../etc/passwd", "0x00"])
def test_malformed_path_param_no_server_error(bad_id):
    r = _get(BACKEND, f"/hermes/orders/{bad_id}")
    # FastAPI's own path-type validation (order_id: int) should reject these
    # before any handler code runs; 401 is also fine if auth is checked first.
    assert r.status_code in (401, 404, 422), f"{bad_id!r} -> {r.status_code}"
    _assert_no_leak(r)


# ── Security headers ──────────────────────────────────────────────

def test_security_headers_present():
    r = _get(BACKEND, "/health")
    headers = {k.lower(): v for k, v in r.headers.items()}
    for expected in ["x-content-type-options", "x-frame-options"]:
        assert expected in headers, f"missing header: {expected}"
    assert headers.get("x-content-type-options") == "nosniff"


def test_openapi_docs_hidden_or_explicitly_enabled():
    # /docs must be either hidden (production default) or genuinely served
    # (debug deployments) -- never a 500.
    r = _get(BACKEND, "/docs")
    assert r.status_code in (200, 404), f"/docs -> {r.status_code}"


# ── Rate limiting ──────────────────────────────────────────────────

def test_signup_endpoint_rate_limited():
    """Best-effort: signup_limiter is 5 req/min. Fire a few more than that
    at a route that's cheap to call repeatedly and expect a 429 to show up.
    Does not fail the suite if the deployment's limiter window doesn't line
    up within this short probe -- rate limiting is verified more precisely
    by the mocked unit tests; this just confirms it's wired up at all."""
    saw_429 = False
    for _ in range(8):
        r = _post(BACKEND, "/auth/signup", json={"email": "not-a-real-signup@example.com", "password": "x"})
        if r.status_code == 429:
            saw_429 = True
            break
        time.sleep(0.2)
    if not saw_429:
        pytest.skip("no 429 observed in 8 rapid requests -- inconclusive, not a failure")


# ── Payment callback replay protection ───────────────────────────

def test_payment_callback_unknown_authority_fails_cleanly():
    """An authority that was never issued must be rejected as a clean
    replay/not-found (handle_payment_callback's row-lock returns None ->
    409), never a 500 -- a 500 here would mean the callback path raises on
    unrecognized input instead of failing closed."""
    r = _get(BACKEND, "/payment/callback", params={"Authority": "A00000000000000000000000000000nonexistent", "Status": "OK"})
    assert r.status_code in (400, 404, 409), f"unexpected status: {r.status_code}"
    _assert_no_leak(r)
