"""Ownership / row-level isolation tests.

Two distinct users must never be able to read or write each other's
conversations, wallet, ledger, API keys, or usage.

The test environment mocks Redis and the async DB (see conftest.py). To make
ownership genuinely verifiable we use two complementary strategies:

1. **Statement introspection** — every privileged query issued by a route is
   compiled and checked to (a) be scoped to the *authenticated* user's id and
   (b) never reference a *different* user's id. This proves the backend
   enforces ownership at the SQL WHERE-clause layer (the actual control that
   prevents cross-user access).

2. **Behavioural (simulated DB)** — a smart session double that actually
   filters an in-memory store by the owner id found in each statement. With a
   "victim" row owned by user B seeded, we assert user A receives 404 / empty
   while user B receives the row. This proves the isolation end-to-end, not
   just that a WHERE clause exists.
"""
import re
import types
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app import app


USER_A = 101
USER_B = 777


# ── Test doubles ─────────────────────────────────────────────

def _row(**kw):
    defaults = {
        'id': 1, 'user_id': None, 'title': 't', 'model': 'm', 'messages': [],
        'created_at': None, 'updated_at': None, 'amount': 0, 'balance_after': 0,
        'reason': 'r', 'daily_limit': 0, 'used_today': 0, 'reset_at': None,
        'name': 'n', 'key_prefix': 'sk-xxxx', 'key_hash': 'h', 'scopes': 'read',
        'active': True, 'revoked_at': None, 'expires_at': None, 'last_used': None,
    }
    defaults.update(kw)
    return types.SimpleNamespace(**{k: v for k, v in defaults.items() if k in defaults})


def _make_result(fetchone=None, fetchall=None):
    r = MagicMock()
    r.fetchone.return_value = fetchone
    r.fetchall.return_value = fetchall if fetchall is not None else []
    r.scalar_one_or_none.return_value = None
    r.scalar_one.return_value = None
    r.rowcount = 0
    return r


def _statement_evidence(stmt, params):
    """Return a searchable string for a captured execute() call."""
    try:
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    except Exception:
        try:
            sql = str(stmt.compile())
        except Exception:
            sql = str(stmt)
    parts = [sql]
    if params:
        parts.append(str(params))
    for attr in ("_bindparams",):
        try:
            vals = getattr(stmt, attr, None)
            if vals:
                parts.extend(str(v) for v in vals.values())
        except Exception:
            pass
    try:
        bp = getattr(stmt, "bound_parameters", None)
        if bp:
            parts.extend(str(v) for v in bp.values())
    except Exception:
        pass
    return " ".join(parts)


class _SessionCapture:
    """Async-session double that records statements and filters an in-memory
    store by the owner id declared in each query (simulating real isolation)."""

    def __init__(self, store=None):
        self.executed = []
        self.added = []
        self.store = store or {}

    # ── introspection helpers ──
    @staticmethod
    def _required_owner(stmt, params):
        try:
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            sql = str(stmt)
        m = re.search(r"user_id\s*=\s*(\d+)", sql)
        if m:
            return int(m.group(1))
        if isinstance(params, dict) and "uid" in params:
            return params["uid"]
        return None

    @staticmethod
    def _table_name(stmt):
        try:
            for f in stmt.get_final_froms():
                name = getattr(f, "name", None)
                if name:
                    return name
        except Exception:
            pass
        try:
            m = re.search(r"from\s+([a-zA-Z_]\w*)", str(stmt), re.IGNORECASE)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    # ── async session interface ──
    async def execute(self, stmt, params=None, *a, **k):
        self.executed.append((stmt, params))
        try:
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            sql = str(stmt)
        owner = None
        m = re.search(r"user_id\s*=\s*(\d+)", sql)
        if m:
            owner = int(m.group(1))
        elif isinstance(params, dict) and "uid" in params:
            owner = params["uid"]
        id_filter = None
        m = re.search(r"\bid\s*=\s*(\d+)", sql)
        if m:
            id_filter = int(m.group(1))
        tname = self._table_name(stmt)
        result = _make_result()

        if "SUM(amount)" in sql:
            rows = self.store.get("ledger", [])
            if owner is not None:
                rows = [r for r in rows if getattr(r, "user_id", None) == owner]
            total = sum(getattr(r, "amount", 0) or 0 for r in rows)
            agg = types.SimpleNamespace(balance=total)
            result.fetchone.return_value = agg
            result.fetchall.return_value = [agg]
            return result

        if tname and tname in self.store:
            rows = self.store[tname]
            if owner is not None:
                rows = [r for r in rows if getattr(r, "user_id", None) == owner]
            if id_filter is not None:
                rows = [r for r in rows if getattr(r, "id", None) == id_filter]
            result.fetchall.return_value = list(rows)
            result.fetchone.return_value = rows[0] if rows else None
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None

    async def refresh(self, obj, *a, **k):
        if not getattr(obj, "id", None):
            obj.id = 1
        return None

    async def get(self, model, ident, *a, **k):
        return None

    async def delete(self, obj):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _make_session(store=None):
    cap = _SessionCapture(store)
    maker = MagicMock(return_value=cap)
    return cap, maker


def _session_for_user(user_id):
    payload = __import__("json").dumps({
        "user_id": user_id,
        "created_at": "2020-01-01T00:00:00",
        "expires_at": "2999-01-01T00:00:00",
    })

    def fake_get(key):
        if isinstance(key, str) and key.startswith("session:"):
            return payload
        return None

    return fake_get


def _call_as(user_id, method, path, json_body=None, store=None):
    cap, maker = _make_session(store)
    fake_get = _session_for_user(user_id)
    from fastapi.testclient import TestClient
    eng = MagicMock()
    eng.dispose = AsyncMock()
    with patch("app.create_async_engine", return_value=eng):
        with TestClient(app) as c:
            with patch("app.async_session", maker), \
                 patch("app.rds.get", side_effect=fake_get), \
                 patch("app.rds.expire", return_value=True), \
                 patch("app.rds.sadd", return_value=True), \
                 patch("app.rds.srem", return_value=True), \
                 patch("app.rds.delete", return_value=True):
                fn = getattr(c, method)
                kwargs: dict = {"cookies": {"session": f"tok{user_id}"}}
                # CSRF middleware requires X-Requested-With for cookie mutations
                if method in ("post", "put", "delete", "patch"):
                    kwargs["headers"] = {"X-Requested-With": "XMLHttpRequest"}
                if json_body is not None:
                    kwargs["json"] = json_body
                resp = fn(path, **kwargs)
    evidence = " ".join(_statement_evidence(s, p) for s, p in cap.executed)
    return resp, cap, evidence


def _call_anon(method, path, json_body=None):
    cap, maker = _make_session(None)
    from fastapi.testclient import TestClient
    eng = MagicMock()
    eng.dispose = AsyncMock()
    with patch("app.create_async_engine", return_value=eng):
        with TestClient(app) as c:
            with patch("app.async_session", maker), \
                 patch("app.rds.get", return_value=None), \
                 patch("app.rds.expire", return_value=True), \
                 patch("app.rds.sadd", return_value=True), \
                 patch("app.rds.srem", return_value=True), \
                 patch("app.rds.delete", return_value=True):
                fn = getattr(c, method)
                kwargs = {}
                if json_body is not None:
                    kwargs["json"] = json_body
                resp = fn(path, **kwargs)
    return resp


# ── Unauthenticated access is rejected ─────────────────────

READ_ENDPOINTS = [
    ("get", "/conversations"),
    ("get", "/wallet"),
    ("get", "/wallet/ledger"),
    ("get", "/api-keys"),
    ("get", "/me/usage"),
]

WRITE_ENDPOINTS = [
    ("post", "/conversations"),
    ("post", "/wallet/topup"),
    ("post", "/api-keys"),
]


@pytest.mark.parametrize("method,path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_unauthenticated_is_rejected(method, path):
    json_body = {"title": "t", "model": "m", "messages": []} if method == "post" and "conversations" in path \
        else {"amount": 100} if "topup" in path else {"name": "k"}
    resp = _call_anon(method, path, json_body=json_body if method == "post" else None)
    assert resp.status_code == 401, f"{method} {path} should reject anon (got {resp.status_code})"


# ── Every privileged query is scoped to the authenticated owner ──

@pytest.mark.parametrize("method,path", READ_ENDPOINTS)
def test_read_scoped_to_owner(method, path):
    resp, cap, ev = _call_as(USER_A, method, path)
    assert str(USER_A) in ev, f"{method} {path} must scope query to owner {USER_A}; evidence={ev!r}"
    assert str(USER_B) not in ev, f"{method} {path} leaked other user {USER_B}; evidence={ev!r}"


@pytest.mark.parametrize("method,path", READ_ENDPOINTS)
def test_read_scoped_to_other_owner(method, path):
    resp, cap, ev = _call_as(USER_B, method, path)
    assert str(USER_B) in ev, f"{method} {path} must scope query to owner {USER_B}; evidence={ev!r}"
    assert str(USER_A) not in ev, f"{method} {path} leaked other user {USER_A}; evidence={ev!r}"


# ── Writes stamp the caller as owner ──

def test_conversation_create_owned_by_caller():
    resp, cap, ev = _call_as(USER_A, "post", "/conversations",
                             json_body={"title": "mine", "model": "m", "messages": []})
    conv = next((o for o in cap.added if type(o).__name__ == "Conversation"), None)
    assert conv is not None, f"expected a Conversation to be added; added={cap.added}"
    assert conv.user_id == USER_A
    assert conv.user_id != USER_B


def test_wallet_topup_owned_by_caller():
    resp, cap, ev = _call_as(USER_A, "post", "/wallet/topup", json_body={"amount": 500})
    entry = next((o for o in cap.added if type(o).__name__ == "Ledger"), None)
    assert entry is not None, f"expected a Ledger to be added; added={cap.added}"
    assert entry.user_id == USER_A
    assert entry.user_id != USER_B


def test_api_key_create_owned_by_caller():
    resp, cap, ev = _call_as(USER_A, "post", "/api-keys", json_body={"name": "k", "scopes": "read"})
    key = next((o for o in cap.added if type(o).__name__ == "ApiKey"), None)
    assert key is not None, f"expected an ApiKey to be added; added={cap.added}"
    assert key.user_id == USER_A
    assert key.user_id != USER_B


# ── Behavioural isolation with a simulated DB ──

def _seed_conversations():
    return {
        "conversations": [
            _row(id=5, user_id=USER_B, title="B secret", model="m"),
            _row(id=6, user_id=USER_A, title="A secret", model="m"),
        ]
    }


def test_cannot_read_other_users_conversation():
    store = _seed_conversations()
    # User A tries to read B's conversation (id=5)
    resp_a, _, _ = _call_as(USER_A, "get", "/conversations/5", store=store)
    assert resp_a.status_code == 404, f"A must not see B's conversation (got {resp_a.status_code}: {resp_a.text})"
    # User B reads their own conversation
    resp_b, _, _ = _call_as(USER_B, "get", "/conversations/5", store=store)
    assert resp_b.status_code == 200
    assert resp_b.json()["title"] == "B secret"


def test_conversation_list_is_per_user():
    store = _seed_conversations()
    resp_a, _, _ = _call_as(USER_A, "get", "/conversations", store=store)
    resp_b, _, _ = _call_as(USER_B, "get", "/conversations", store=store)
    a_ids = [c["id"] for c in resp_a.json()]
    b_ids = [c["id"] for c in resp_b.json()]
    assert a_ids == [6], f"A should only see their own conversation; got {a_ids}"
    assert b_ids == [5], f"B should only see their own conversation; got {b_ids}"


def test_cannot_read_other_users_ledger():
    store = {"ledger": [
        _row(id=1, user_id=USER_B, amount=1000, balance_after=1000),
        _row(id=2, user_id=USER_A, amount=50, balance_after=50),
    ]}
    resp_a, _, _ = _call_as(USER_A, "get", "/wallet/ledger", store=store)
    resp_b, _, _ = _call_as(USER_B, "get", "/wallet/ledger", store=store)
    assert [r["id"] for r in resp_a.json()] == [2], \
        f"A should only see their own ledger rows; got {resp_a.json()}"
    assert len(resp_b.json()) == 1 and resp_b.json()[0]["id"] == 1


def test_cannot_read_other_users_wallet_balance():
    store = {"ledger": [
        _row(id=1, user_id=USER_B, amount=7777, balance_after=7777),
        _row(id=2, user_id=USER_A, amount=42, balance_after=42),
    ]}
    resp_a, _, _ = _call_as(USER_A, "get", "/wallet", store=store)
    resp_b, _, _ = _call_as(USER_B, "get", "/wallet", store=store)
    # A's balance must come only from A's rows (42), never B's.
    assert resp_a.json()["balance"] == 42, f"A balance leaked; got {resp_a.json()}"
    assert resp_b.json()["balance"] == 7777


def test_cannot_read_other_users_api_keys():
    store = {"api_keys": [
        _row(id=1, user_id=USER_B, name="B-key"),
        _row(id=2, user_id=USER_A, name="A-key"),
    ]}
    resp_a, _, _ = _call_as(USER_A, "get", "/api-keys", store=store)
    resp_b, _, _ = _call_as(USER_B, "get", "/api-keys", store=store)
    a_ids = [k["id"] for k in resp_a.json()]
    b_ids = [k["id"] for k in resp_b.json()]
    assert a_ids == [2], f"A should only see their own key; got {a_ids}"
    assert b_ids == [1], f"B should only see their own key; got {b_ids}"


def test_cannot_read_other_users_usage():
    store = {"quota": [
        _row(user_id=USER_B, daily_limit=9999, used_today=3),
        _row(user_id=USER_A, daily_limit=500, used_today=1),
    ]}
    resp_a, _, _ = _call_as(USER_A, "get", "/me/usage", store=store)
    resp_b, _, _ = _call_as(USER_B, "get", "/me/usage", store=store)
    assert resp_a.json()["user_id"] == USER_A
    assert resp_a.json()["daily_limit"] == 500
    assert resp_b.json()["user_id"] == USER_B
    assert resp_b.json()["daily_limit"] == 9999
    # Make sure A's payload never carries B's quota numbers.
    assert resp_a.json()["daily_limit"] != 9999


def test_revoke_api_key_is_scoped():
    """Revoking a key must filter by owner; A cannot revoke B's key."""
    # Capture the UPDATE statement issued for a revoke attempt.
    cap, maker = _make_session(None)
    fake_get = _session_for_user(USER_A)
    from fastapi.testclient import TestClient
    eng = MagicMock()
    eng.dispose = AsyncMock()
    with patch("app.create_async_engine", return_value=eng):
        with TestClient(app) as c:
            with patch("app.async_session", maker), \
                 patch("app.rds.get", side_effect=fake_get), \
                 patch("app.rds.expire", return_value=True), \
                 patch("app.rds.sadd", return_value=True), \
                 patch("app.rds.srem", return_value=True), \
                 patch("app.rds.delete", return_value=True):
                c.delete("/api-keys/999", cookies={"session": "tokA"}, headers={"X-Requested-With": "XMLHttpRequest"})
    ev = " ".join(_statement_evidence(s, p) for s, p in cap.executed)
    assert str(USER_A) in ev, f"revoke must be scoped to owner A; evidence={ev!r}"
    assert str(USER_B) not in ev
