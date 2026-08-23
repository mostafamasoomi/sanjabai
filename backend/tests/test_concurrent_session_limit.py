"""MAX_CONCURRENT_SESSIONS is a security control that must actually run.

`track_session` was fully implemented and never called: it was imported into
auth.py and nothing invoked it, so the 3-session cap silently did nothing from
the day it was written (session 11 audit). A dead control is worse than no
control -- it reads as implemented.

These tests pin the two things that make it real: the limit revokes the oldest
session once exceeded, and it books sessions into `sessions:{uid}` -- the same
per-user set `_create_session` and `/auth/logout-all` use. It used to keep a
private `active_sessions:{uid}` set, so a revoke here left the token behind in
the set logout-all actually walks.

Redis is the conftest AsyncMock; a real Redis is never touched.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import security


def _request(ip: str = '1.2.3.4', ua: str = 'pytest') -> MagicMock:
    r = MagicMock()
    r.headers = {'user-agent': ua}
    r.client = MagicMock(host=ip)
    return r


class _FakeRedis:
    """Just enough Redis for track_session: string keys + one set per user."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.deleted: list[str] = []

    async def setex(self, key, ttl, value):
        self.kv[key] = value

    async def get(self, key):
        return self.kv.get(key)

    async def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    async def expire(self, key, ttl):
        return True

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def srem(self, key, member):
        self.sets.get(key, set()).discard(member)

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.deleted.append(k)


@pytest.fixture
def fake_redis():
    r = _FakeRedis()
    with patch.object(security, '_get_redis', lambda: r):
        yield r


async def _seed(redis, uid: int, tokens_with_times: list[tuple[str, str]]):
    """Put pre-existing sessions in the canonical set with known created_at."""
    for tok, created in tokens_with_times:
        redis.sets.setdefault(f'sessions:{uid}', set()).add(tok)
        redis.kv[f'session_meta:{tok}'] = json.dumps({
            'user_id': uid, 'ip': '9.9.9.9', 'user_agent': 'old',
            'created_at': created, 'last_seen': created,
        })


class TestLimitIsEnforced:
    @pytest.mark.asyncio
    async def test_oldest_session_is_revoked_when_limit_exceeded(self, fake_redis):
        uid = 7
        await _seed(fake_redis, uid, [
            ('tok_oldest', '2026-01-01T00:00:00Z'),
            ('tok_middle', '2026-06-01T00:00:00Z'),
            ('tok_recent', '2026-08-01T00:00:00Z'),
        ])
        # A 4th login pushes the user over MAX_CONCURRENT_SESSIONS (3).
        await security.track_session('tok_new', uid, _request())

        assert 'session:tok_oldest' in fake_redis.deleted
        assert 'session_meta:tok_oldest' in fake_redis.deleted
        assert 'tok_oldest' not in fake_redis.sets[f'sessions:{uid}']
        # and only the oldest went
        assert 'tok_middle' in fake_redis.sets[f'sessions:{uid}']
        assert 'tok_new' in fake_redis.sets[f'sessions:{uid}']

    @pytest.mark.asyncio
    async def test_under_the_limit_nothing_is_revoked(self, fake_redis):
        uid = 8
        await _seed(fake_redis, uid, [('tok_a', '2026-01-01T00:00:00Z')])
        await security.track_session('tok_b', uid, _request())
        assert not [d for d in fake_redis.deleted if d.startswith('session:')]
        assert fake_redis.sets[f'sessions:{uid}'] == {'tok_a', 'tok_b'}


class TestUsesTheCanonicalSet:
    @pytest.mark.asyncio
    async def test_session_is_booked_into_the_same_set_logout_all_reads(self, fake_redis):
        # dependencies._create_session and /auth/logout-all both use
        # `sessions:{uid}`; a private second set is how a revoked token
        # survived in the set that actually gets walked.
        await security.track_session('tok_x', 42, _request())
        assert fake_redis.sets['sessions:42'] == {'tok_x'}
        assert 'active_sessions:42' not in fake_redis.sets

    @pytest.mark.asyncio
    async def test_metadata_is_recorded_for_forensics(self, fake_redis):
        await security.track_session('tok_y', 43, _request(ip='5.6.7.8', ua='curl/8'))
        meta = json.loads(fake_redis.kv['session_meta:tok_y'])
        assert meta['user_id'] == 43
        assert meta['user_agent'] == 'curl/8'
        assert meta['created_at'] and meta['last_seen']


class TestNeverRaises:
    @pytest.mark.asyncio
    async def test_a_redis_failure_does_not_break_login(self):
        # track_session runs inside the login path: if Redis is down, the user
        # must still get their session, not a 500.
        broken = AsyncMock()
        broken.setex.side_effect = RuntimeError('redis down')
        with patch.object(security, '_get_redis', lambda: broken):
            await security.track_session('tok_z', 1, _request())  # must not raise
