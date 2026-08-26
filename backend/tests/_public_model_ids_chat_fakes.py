"""Shared fakes for the chat.py side of the public model id indirection
(migrations/0028_public_model_ids.sql).

Not a test file itself (no ``test_`` prefix, so pytest never collects it) --
imported by tests/test_public_model_ids_chat.py. Split out of the original
tests/test_public_model_ids.py (which grew past the 500-line cap) so that
test file doesn't have to carry ~200 lines of fake-session/fake-http
plumbing alongside its test classes -- see tests/_entitlements_order_by.py
and tests/_user_quota_fakes.py for the established pattern this follows.

No test using these fakes makes a real network or DB call: the DB session
proxy and the outbound httpx client are always faked, following this
suite's existing conventions (see test_web_search.py's bypass fixture and
test_billing_loss_paths.py's `_FakeSession`).
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import database as _db


# A small fake catalog mirroring migrations/0028_public_model_ids.sql's shape.
# id == provider_model_id always in this codebase (model_discovery.py's
# sync_provider upserts both from the same upstream string), public_id is
# None for rows the migration deliberately leaves unlisted (collision losers,
# or anything an admin hasn't named yet).
_FAKE_CATALOG = [
    {'id': 'bynara/mistral-large', 'provider_model_id': 'bynara/mistral-large', 'public_id': 'sanjab/mistral-large'},
    # Collision loser: a bare, pre-migration id for a degraded litellm route
    # that lost the public_id assignment to 'bynara/mistral-large' above.
    # Keeps its own id/route/price, must still work as a chat id, but must
    # never appear in public listings.
    {'id': 'mistral-large', 'provider_model_id': 'mistral-large', 'public_id': None},
    {'id': 'bynara/mimo-v2.5-free', 'provider_model_id': 'bynara/mimo-v2.5-free', 'public_id': 'sanjab/mimo-v2.5'},
    {'id': 'kr/claude-sonnet-4', 'provider_model_id': 'kr/claude-sonnet-4', 'public_id': 'sanjab/claude-sonnet-4'},
    {'id': 'tencent-hy3', 'provider_model_id': 'tencent-hy3', 'public_id': None},
    # Precedence fixture: 'sanjab/collide' is BOTH a real public_id (winning
    # row -> 'winner/collide') and the raw `id` of a completely unrelated
    # row (-> 'legacy/collide-loser'). public_id must win.
    {'id': 'sanjab/collide', 'provider_model_id': 'legacy/collide-loser', 'public_id': None},
    {'id': 'winner/collide', 'provider_model_id': 'winner/collide', 'public_id': 'sanjab/collide'},
]


def _resolve_rows(catalog):
    """Build the (key, provider_model_id) rows chat._MODEL_RESOLVE_SQL's
    `ORDER BY rnk` would produce for `catalog`: every public_id row first
    (rnk 0), then every provider_model_id row (rnk 1), then every id row
    (rnk 2) -- matching the UNION ALL ... ORDER BY rnk query exactly, so the
    cache-build loop's "first occurrence per key wins" logic is exercised
    the same way it would be against a real Postgres."""
    rows = []
    for c in catalog:
        if c.get('public_id'):
            rows.append(types.SimpleNamespace(key=c['public_id'], provider_model_id=c['provider_model_id']))
    for c in catalog:
        if c.get('provider_model_id'):
            rows.append(types.SimpleNamespace(key=c['provider_model_id'], provider_model_id=c['provider_model_id']))
    for c in catalog:
        if c.get('id'):
            rows.append(types.SimpleNamespace(key=c['id'], provider_model_id=c['provider_model_id']))
    return rows


class _CatalogFakeSession:
    """Fake AsyncSession serving every model_catalog-related query chat.py
    issues, backed by one small in-memory `catalog` (list of
    {id, provider_model_id, public_id} dicts) -- shared by
    _resolve_public_model's resolve query, get_working_models(), and
    _is_model_allowed()'s direct-row-exists fallback, so all three see a
    mutually consistent picture instead of three unrelated canned results."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt, params=None, *a, **k):
        text_sql = str(stmt)
        result = MagicMock()
        if 'precedence' in text_sql:
            # chat._MODEL_RESOLVE_SQL
            result.fetchall.return_value = _resolve_rows(self.catalog)
            return result
        if 'SELECT 1 FROM model_catalog' in text_sql:
            # chat._is_model_allowed's direct-row-exists fallback
            mid = (params or {}).get('mid')
            hit = any(
                c.get('provider_model_id') == mid or c.get('id') == mid or c.get('public_id') == mid
                for c in self.catalog
            )
            result.fetchone.return_value = (1,) if hit else None
            return result
        if 'input_per_million' in text_sql:
            # chat._record_usage's price lookup (`WHERE provider_model_id = :mid`).
            # Returns a small sane price row for any known provider_model_id,
            # None otherwise (the real L2 fallback-ceiling path) -- this must
            # never return an unconfigured MagicMock, which would make
            # `int(price_row.input_per_million or 0)` blow up downstream.
            mid = (params or {}).get('mid')
            hit = any(c.get('provider_model_id') == mid for c in self.catalog)
            result.fetchone.return_value = (
                types.SimpleNamespace(input_per_million=1000, output_per_million=1000) if hit else None
            )
            return result
        if 'FROM model_catalog' in text_sql and 'availability' in text_sql:
            # chat.get_working_models()
            rows = [
                types.SimpleNamespace(
                    provider_model_id=c['provider_model_id'], id=c['id'], public_id=c.get('public_id'),
                )
                for c in self.catalog
            ]
            result.fetchall.return_value = rows
            return result
        result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    async def commit(self):
        return None


def _patch_resolve_db(catalog=_FAKE_CATALOG):
    """Patch database._real_async_session (the state backing every module's
    shared `async_session` proxy -- see conftest.py's mock_async_session
    fixture docstring) so every `async with async_session() as session` in
    chat.py yields a `_CatalogFakeSession` backed by `catalog`."""
    session = _CatalogFakeSession(catalog)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return None

    maker = MagicMock(return_value=_Ctx())
    return patch.object(_db, '_real_async_session', maker)


class _FakeProvider:
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _billing_mock():
    """A BillingService replacement whose reserve()/release() never touch a
    real DB -- mirrors test_web_search.py's helper of the same name."""
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
    instance.release = AsyncMock(return_value=None)
    instance.settle = AsyncMock(return_value=None)
    return MagicMock(return_value=instance)


def _upstream_response(body: dict | None = None, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


def _patched_http(capture: dict | None = None, body: dict | None = None):
    fake = MagicMock()
    if capture is not None:
        async def _post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            capture['url'] = url
            return _upstream_response(body)
        fake.post = _post
    else:
        fake.post = AsyncMock(return_value=_upstream_response(body))
    return fake


AUTH_HEADERS = {'Authorization': 'Bearer test-token'}


def _table_name(stmt):
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            name = getattr(f, "name", None)
            if name:
                return name
    except Exception:
        pass
    return None


class _RecordUsageFakeSession:
    """Minimal session double covering exactly the statements
    chat._record_usage / SqlBillingRepo issue -- same shape as
    test_billing_loss_paths.py's `_FakeSession` (kept local to this module
    so it doesn't need to import another test module)."""

    def __init__(self, wallet_balance, price_by_mid=None):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price_by_mid = price_by_mid or {}
        self.added = []
        self.last_price_lookup_mid = None

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        text_sql = str(stmt)
        if "model_catalog" in text_sql:
            mid = (params or {}).get('mid')
            self.last_price_lookup_mid = mid
            result.fetchone.return_value = self.price_by_mid.get(mid)
            return result
        tname = _table_name(stmt)
        if tname == "wallet":
            if type(stmt).__name__ == "Update":
                p = stmt.compile().params
                if "balance" in p:
                    self.wallet.balance = p["balance"]
            else:
                result.fetchone.return_value = (self.wallet,)
            return result
        if tname == "quota":
            if type(stmt).__name__ == "Update":
                return result
            result.fetchone.return_value = None
            return result
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _price(inp=1_000_000, out=1_000_000):
    return types.SimpleNamespace(input_per_million=inp, output_per_million=out)
