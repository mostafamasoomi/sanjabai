"""Shared fakes for the per-user aggregate quota gate (services/user_quota.py).

Not a test file itself (no ``test_`` prefix, so pytest never collects it) --
imported by both ``test_user_quota_gate.py`` (behaviour/boundary/window/
fail-open/status tests against these fakes) and ``test_user_quota_wiring.py``
(the end-to-end HTTP tests, which drive the real gate through these same
fakes). Split out of the original tests/test_user_quota.py so neither test
file has to duplicate this setup -- see tests/_entitlements_order_by.py for
the established pattern this follows.

The fake session does NOT hand back a canned fetchall(): it evaluates the
real predicate (active / not expired / rate_limit_per_window IS NOT NULL AND
> 0 / MAX across packages) against in-memory rows, so a test that says "the
expired package must not count" is actually exercising that rule rather than
a hardcoded answer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from services import user_quota


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeRedis:
    """Exactly the commands services.user_quota issues: get, ttl, incrby,
    expire. TTLs do not count down with wall-clock time; ``expire_now``
    simulates a window running out."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("simulated redis outage")

    async def get(self, key):
        self._check()
        return self.store.get(key)

    async def incrby(self, key, amount):
        self._check()
        cur = int(self.store.get(key, '0')) + int(amount)
        self.store[key] = str(cur)
        return cur

    async def expire(self, key, seconds):
        self._check()
        if key in self.store:
            self.ttls[key] = int(seconds)
            return True
        return False

    async def ttl(self, key):
        self._check()
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    # ── test-only helpers ──
    def seed(self, uid: int, used: int, ttl: int = 1234):
        self.store[user_quota._msg_key(uid)] = str(used)
        self.ttls[user_quota._msg_key(uid)] = ttl

    def used(self, uid: int) -> int:
        return int(self.store.get(user_quota._msg_key(uid), '0'))

    def expire_now(self, uid: int):
        self.store.pop(user_quota._msg_key(uid), None)
        self.ttls.pop(user_quota._msg_key(uid), None)


def _row(d: dict):
    m = MagicMock()
    m._mapping = dict(d)
    return m


class _FakePackageDB:
    """In-memory stand-in for package_entitlement JOIN credit_packages."""

    def __init__(self):
        self.packages: dict[str, dict] = {}
        self.entitlements: list[dict] = []
        self.fail = False

    def add_package(self, package_id: str, rate_limit_per_window=None):
        self.packages[package_id] = {'id': package_id, 'rate_limit_per_window': rate_limit_per_window}

    def add_entitlement(self, uid: int, package_id: str, *, active=True, expires_at=None):
        self.entitlements.append({
            'user_id': uid, 'package_id': package_id,
            'active': active, 'expires_at': expires_at,
        })

    def max_rate_limit(self, uid: int):
        """The real WHERE clause, re-implemented -- see module docstring for
        why this is paired with the SQL-text assertions in
        test_user_quota_wiring.py."""
        now = _utcnow()
        best = None
        for e in self.entitlements:
            if e['user_id'] != uid:
                continue
            if not e['active']:
                continue
            if e['expires_at'] is not None and e['expires_at'] <= now:
                continue
            pkg = self.packages.get(e['package_id'])
            if pkg is None:
                continue  # the JOIN drops it
            q = pkg['rate_limit_per_window']
            if q is None or q <= 0:
                continue
            best = q if best is None else max(best, q)
        return best


class _FakeSession:
    def __init__(self, db: _FakePackageDB):
        self.db = db

    async def execute(self, stmt, params=None):
        if self.db.fail:
            raise RuntimeError("simulated database outage")
        params = params or {}
        sql = str(stmt)
        result = MagicMock()
        result.fetchone.return_value = None
        if 'FROM package_entitlement pe' in sql:
            result.fetchone.return_value = _row(
                {'limit_value': self.db.max_rate_limit(params['uid'])}
            )
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _session_factory(db: _FakePackageDB):
    def factory():
        return _FakeSession(db)
    return factory
