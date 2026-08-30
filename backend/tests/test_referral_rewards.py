"""Tests for services/referral.py -- the referral reward.

── Owner decision, 2026-08-30 (see services/referral.py's module docstring
for the full reasoning) ───────────────────────────────────────────────────
The INVITEE leg is now paid IMMEDIATELY at signup, via
services.referral.credit_invitee_signup_reward(), called from auth.py's
signup handler right after record_attribution() (same session, same
referrer-exists branch). This supersedes the 2026-08-28 decision that both
legs waited for the invitee's first payment. The INVITER leg is unaffected:
it still only pays via services.referral.settle_on_first_payment(), called
from payment_endpoints.py after the invitee's first successful payment.
SINGLE-PAY for the invitee leg is enforced two ways at once: the same
idempotency_key (`referral:invitee:{invitee_id}`) is used by both
functions (credit_wallet's own idempotency guard), AND
settle_on_first_payment() detects a non-zero invitee_amount_toman already
on the row and skips crediting that leg again -- see
test_single_pay_signup_then_settle_credits_invitee_exactly_once below,
which is this file's highest-risk test.

auth.py's signup handler calls record_attribution() (still 'pending'
bookkeeping only, never touches a wallet -- see
test_signup_time_attribution_never_credits_a_wallet below) followed by
credit_invitee_signup_reward() (the actual wallet touch). Both must never
raise -- a referral bookkeeping or crediting failure must not fail a
signup.

No live Postgres is available (tests/conftest.py), so these tests drive
services.referral against a small in-memory fake standing in for
`referral_reward` and `app_setting`, following the same pattern
tests/test_entitlements.py uses for services/entitlements.py: every
statement in referral.py is a raw sqlalchemy.text() clause, so the fake
session dispatches on a distinctive substring of the compiled SQL text.

Most tests here monkeypatch services.billing.credit_wallet to an AsyncMock
and assert on ITS call arguments (txn_type, idempotency_key, amount) --
services/billing.py's own credit_wallet correctness (balance math,
idempotency-by-key, wallet creation) is already covered by
tests/test_billing.py, so this file's job is only the referral
orchestration around it. The SINGLE-PAY test is the one exception: it
deliberately exercises the REAL credit_wallet against a shared
MemoryBillingRepo so the single-pay claim is proven against actual wallet
balance math, not just call-count bookkeeping.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import services.referral as referral_mod
from services.money import Money


# ── fake DB ──────────────────────────────────────────────────────────────

def _row(**cols):
    """Mimic a SQLAlchemy Row well enough for both attribute access
    (`row.id`) and `dict(row._mapping)`."""
    m = MagicMock()
    for k, v in cols.items():
        setattr(m, k, v)
    m._mapping = dict(cols)
    return m


class _FakeReferralDB:
    """In-memory stand-in for `referral_reward` and the three
    `referral_*` app_setting rows."""

    def __init__(self):
        self.rows: dict[int, dict] = {}  # keyed by invitee_id
        self._next_id = 1
        self.settings: dict[str, int] = {}
        self.commits = 0

    def seed_config(self, *, inviter=0, invitee=0, cap=10):
        self.settings = {
            'referral_reward_toman': inviter,
            'referral_invitee_reward_toman': invitee,
            'referral_reward_cap': cap,
        }

    def add_pending(self, inviter_id: int, invitee_id: int) -> int:
        rid = self._next_id
        self._next_id += 1
        self.rows[invitee_id] = {
            'id': rid, 'inviter_id': inviter_id, 'invitee_id': invitee_id,
            'status': 'pending', 'inviter_amount_toman': 0, 'invitee_amount_toman': 0,
        }
        return rid

    def add_paid(self, inviter_id: int, invitee_id: int, **cols) -> int:
        rid = self.add_pending(inviter_id, invitee_id)
        self.rows[invitee_id]['status'] = 'paid'
        self.rows[invitee_id].update(cols)
        return rid


class _FakeSession:
    """Dispatches services.referral's raw SQL against a _FakeReferralDB."""

    def __init__(self, db: _FakeReferralDB, *, boom: bool = False):
        self.db = db
        self._boom = boom

    async def execute(self, stmt, params=None):
        if self._boom:
            raise RuntimeError('db down')
        sql = str(stmt)
        params = params or {}
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []

        if 'FROM app_setting' in sql:
            rows = [
                _row(setting_key=k, value=v)
                for k, v in self.db.settings.items() if k in params.get('keys', [])
            ]
            result.fetchall.return_value = rows
            return result

        if sql.strip().startswith('INSERT INTO referral_reward'):
            inviter_id, invitee_id = params['inviter_id'], params['invitee_id']
            if invitee_id not in self.db.rows:  # ON CONFLICT (invitee_id) DO NOTHING
                self.db.add_pending(inviter_id, invitee_id)
            return result

        if "UPDATE referral_reward SET status = 'capped'" in sql:
            for row in self.db.rows.values():
                if row['id'] == params['id'] and row['status'] == 'pending':
                    row['status'] = 'capped'
            return result

        if "UPDATE referral_reward SET status = 'paid'" in sql:
            for row in self.db.rows.values():
                if row['id'] == params['id'] and row['status'] == 'pending':
                    row['status'] = 'paid'
                    row['inviter_amount_toman'] = params['inviter_amount']
                    row['invitee_amount_toman'] = params['invitee_amount']
            return result

        if 'SET invitee_amount_toman' in sql:
            # credit_invitee_signup_reward()'s signup-time stamp -- only
            # fires on a still-pending, still-zero row (mirrors the real
            # WHERE clause's guard against double-stamping).
            row = self.db.rows.get(params['invitee_id'])
            if row is not None and row['status'] == 'pending' and row['invitee_amount_toman'] == 0:
                row['invitee_amount_toman'] = params['amount']
            return result

        if 'referral_count' in sql:
            # stats()
            inviter_id = params['inviter_id']
            matches = [r for r in self.db.rows.values() if r['inviter_id'] == inviter_id]
            paid = [r for r in matches if r['status'] == 'paid']
            pending = [r for r in matches if r['status'] == 'pending']
            total = sum(r['inviter_amount_toman'] for r in paid)
            result.fetchone.return_value = _row(
                referral_count=len(matches), paid_count=len(paid),
                pending_count=len(pending), total_bonus_toman=total,
            )
            return result

        if 'AS c FROM referral_reward' in sql:
            # cap count
            inviter_id = params['inviter_id']
            count = sum(
                1 for r in self.db.rows.values()
                if r['inviter_id'] == inviter_id and r['status'] == 'paid'
            )
            result.fetchone.return_value = _row(c=count)
            return result

        if "status = 'pending'" in sql and 'invitee_id' in params and sql.strip().startswith('SELECT'):
            # SELECT pending by invitee
            row = self.db.rows.get(params['invitee_id'])
            if row is not None and row['status'] == 'pending':
                result.fetchone.return_value = _row(
                    id=row['id'], inviter_id=row['inviter_id'], invitee_id=row['invitee_id'],
                    invitee_amount_toman=row['invitee_amount_toman'],
                )
            return result

        raise AssertionError(f'unrecognized SQL in fake session: {sql}')

    async def commit(self):
        self.db.commits += 1


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _reset_cache():
    """services.referral.config() caches for 60s in a module global --
    without this, whichever test runs first would poison every test after
    it in the same process."""
    referral_mod.invalidate()
    yield
    referral_mod.invalidate()


@pytest.fixture
def db():
    return _FakeReferralDB()


@pytest.fixture
def patched(monkeypatch, db):
    monkeypatch.setattr(referral_mod, 'async_session', lambda: _Ctx(_FakeSession(db)))
    return db


@pytest.fixture
def credit(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(referral_mod, 'credit_wallet', mock)
    return mock


# ── (a) record_attribution never credits a wallet ───────────────────────

@pytest.mark.asyncio
async def test_signup_time_attribution_never_credits_a_wallet(db, credit):
    """record_attribution() -- the bookkeeping half of auth.py's signup
    handler -- writes a 'pending' row and must never touch the wallet
    itself. (The actual signup-time wallet touch is a SEPARATE call,
    credit_invitee_signup_reward(), covered below.)"""
    session = _FakeSession(db)
    await referral_mod.record_attribution(session, inviter_id=1, invitee_id=2)

    assert db.rows[2]['status'] == 'pending'
    assert db.rows[2]['inviter_id'] == 1
    credit.assert_not_called()


# ── (b) settle_on_first_payment credits both legs ──────────────────────
#
# NOTE: credit_invitee_signup_reward() itself (the signup-time invitee
# bonus) and the SINGLE-PAY interaction between it and settle_on_first_payment
# are tested in tests/test_signup_bonus.py, not here -- this file was
# already close to the house 500-line cap, and that new surface belongs in
# its own file per the cap's "new surface goes in a new file" rule. It
# reuses this file's _FakeReferralDB/_FakeSession/fixtures via import.

@pytest.mark.asyncio
async def test_settle_credits_both_legs_with_referral_bonus_txn_type(patched, credit):
    patched.seed_config(inviter=5000, invitee=2000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)

    result = await referral_mod.settle_on_first_payment(2)

    assert result is not None and result['capped'] is False
    assert credit.await_count == 2
    # Inspect each call's positional/keyword args directly.
    seen = {}
    for call in credit.await_args_list:
        args, kwargs = call.args, call.kwargs
        user_id = args[1]
        amount = args[2]
        seen[user_id] = (amount, kwargs.get('txn_type'), kwargs.get('idempotency_key'))

    assert seen[1][0] == Money(5000)
    assert seen[1][1] == 'referral_bonus'
    assert seen[1][2] == 'referral:inviter:1:2'

    assert seen[2][0] == Money(2000)
    assert seen[2][1] == 'referral_bonus'
    assert seen[2][2] == 'referral:invitee:2'

    assert patched.rows[2]['status'] == 'paid'
    assert patched.rows[2]['inviter_amount_toman'] == 5000
    assert patched.rows[2]['invitee_amount_toman'] == 2000


# ── (پ) idempotency: two calls settle once ──────────────────────────────

@pytest.mark.asyncio
async def test_settle_called_twice_credits_only_once(patched, credit):
    patched.seed_config(inviter=5000, invitee=2000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)

    first = await referral_mod.settle_on_first_payment(2)
    second = await referral_mod.settle_on_first_payment(2)

    assert first is not None and first['capped'] is False
    assert second is None  # no pending row left to find
    assert credit.await_count == 2  # not 4 -- the second call credited nothing


# NOTE: the SINGLE-PAY interaction (credit_invitee_signup_reward() then
# settle_on_first_payment() for the same invitee) and the "inviter leg
# unaffected when the invitee already got paid at signup" case both live in
# tests/test_signup_bonus.py -- see the note above the (b) section header.


# ── (ت) cap ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_settle_marks_capped_and_credits_nothing_once_cap_reached(patched, credit):
    patched.seed_config(inviter=5000, invitee=2000, cap=2)
    patched.add_paid(inviter_id=1, invitee_id=100, inviter_amount_toman=5000)
    patched.add_paid(inviter_id=1, invitee_id=101, inviter_amount_toman=5000)
    patched.add_pending(inviter_id=1, invitee_id=200)

    result = await referral_mod.settle_on_first_payment(200)

    assert result == {'capped': True, 'inviter_id': 1, 'invitee_id': 200}
    assert patched.rows[200]['status'] == 'capped'
    credit.assert_not_called()


# ── (ث) self-referral makes no row ──────────────────────────────────────

@pytest.mark.asyncio
async def test_self_referral_records_nothing(db, credit):
    session = _FakeSession(db)
    await referral_mod.record_attribution(session, inviter_id=7, invitee_id=7)

    assert db.rows == {}
    credit.assert_not_called()


# ── (ج) zero-amount seed leaves the row pending, credits nothing ───────

@pytest.mark.asyncio
async def test_zero_configured_amounts_is_a_feature_off_noop(patched, credit):
    patched.seed_config(inviter=0, invitee=0, cap=10)  # migration 0051's actual seed
    patched.add_pending(inviter_id=1, invitee_id=2)

    result = await referral_mod.settle_on_first_payment(2)

    assert result is None
    assert patched.rows[2]['status'] == 'pending'
    credit.assert_not_called()


# ── (چ) an exception in the settle path never escapes ──────────────────

@pytest.mark.asyncio
async def test_settle_never_raises_on_db_error(monkeypatch, db, credit):
    monkeypatch.setattr(referral_mod, 'async_session', lambda: _Ctx(_FakeSession(db, boom=True)))
    result = await referral_mod.settle_on_first_payment(2)
    assert result is None


@pytest.mark.asyncio
async def test_record_attribution_never_raises_on_db_error():
    class _BoomSession:
        async def execute(self, *a, **k):
            raise RuntimeError('db down')

        async def commit(self):
            raise AssertionError('must not be reached')

    # Must not raise.
    await referral_mod.record_attribution(_BoomSession(), inviter_id=1, invitee_id=2)


# ── duplicate attribution is a no-op (invitee_id UNIQUE / ON CONFLICT) ──

@pytest.mark.asyncio
async def test_duplicate_attribution_does_not_overwrite_existing_row(db):
    session = _FakeSession(db)
    await referral_mod.record_attribution(session, inviter_id=1, invitee_id=2)
    await referral_mod.record_attribution(session, inviter_id=999, invitee_id=2)

    assert db.rows[2]['inviter_id'] == 1  # the first attribution wins
    assert len(db.rows) == 1


# ── stats() ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_sums_only_paid_rows(patched):
    patched.add_paid(inviter_id=1, invitee_id=10, inviter_amount_toman=5000)
    patched.add_paid(inviter_id=1, invitee_id=11, inviter_amount_toman=3000)
    patched.add_pending(inviter_id=1, invitee_id=12)

    result = await referral_mod.stats(1)

    assert result['referral_count'] == 3
    assert result['paid_count'] == 2
    assert result['pending_count'] == 1
    assert result['total_bonus_toman'] == 8000


@pytest.mark.asyncio
async def test_stats_never_raises_fails_safe_to_zero(monkeypatch, db):
    monkeypatch.setattr(referral_mod, 'async_session', lambda: _Ctx(_FakeSession(db, boom=True)))
    result = await referral_mod.stats(1)
    assert result == {
        'referral_count': 0, 'paid_count': 0, 'pending_count': 0, 'total_bonus_toman': 0,
    }


# ── config() cache / fail-safe defaults ─────────────────────────────────

@pytest.mark.asyncio
async def test_config_defaults_match_migration_0051_seed(monkeypatch):
    """async_session is None (DB unreachable) -- config() must fail safe to
    the hardcoded defaults, and those defaults must be all-zero amounts /
    cap 10, exactly what migration 0051 seeds."""
    monkeypatch.setattr(referral_mod, 'async_session', None)
    cfg = await referral_mod.config()
    assert cfg == {
        'referral_reward_toman': 0,
        'referral_invitee_reward_toman': 0,
        'referral_reward_cap': 10,
    }


# ── (c) wiring: the two call sites that make any of the above reachable ─────
#
# Every case above calls services/referral.py directly. That leaves the part
# that actually makes the feature exist -- payment_endpoints.py settling on a
# successful payment, and auth.py recording the attribution at signup --
# completely uncovered, which was measured, not assumed: deleting BOTH call
# sites leaves all 24 cases in this file and test_credit_paths.py green. The
# referral feature would be structurally dead in production with a fully
# green suite.
#
# These scan the AST rather than the text: a `grep` for the function name
# matches an import, a comment or a docstring, none of which call anything.

import ast
import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _awaited_call_names(path: pathlib.Path) -> set[str]:
    """Every function name that is actually awaited somewhere in `path`."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if isinstance(fn, ast.Name):
            names.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            names.add(fn.attr)
    return names


def test_payment_callback_settles_the_referral():
    # The owner's decision is that the reward is paid here and nowhere else.
    # If this call disappears, an invite is recorded forever and never pays.
    assert 'settle_on_first_payment' in _awaited_call_names(_BACKEND / 'payment_endpoints.py')


def test_signup_records_the_referral_attribution():
    # Without this, there is no 'pending' row for the payment callback to
    # find later, so the settle site above becomes a permanent no-op.
    assert 'record_attribution' in _awaited_call_names(_BACKEND / 'auth.py')


# NOTE: the wiring guard for credit_invitee_signup_reward() (auth.py must
# call it right after record_attribution()) lives in
# tests/test_signup_bonus.py, not here -- see the note above the (b)
# section header for why the new surface moved to its own file.


def test_the_settlement_cannot_fail_the_payment_it_follows():
    """The settle call must sit inside a `try` whose handler does not re-raise.

    A referral bug must never turn a real, already-captured payment into an
    error for the user -- the wallet has been credited by this point.
    """
    tree = ast.parse((_BACKEND / 'payment_endpoints.py').read_text(encoding='utf-8'))
    guarded = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if 'settle_on_first_payment' not in {
            n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }:
            continue
        # Every handler must swallow: no bare `raise`, no `raise X`.
        if node.handlers and not any(
            isinstance(n, ast.Raise) for h in node.handlers for n in ast.walk(h)
        ):
            guarded = True
    assert guarded, 'settle_on_first_payment must run inside a try/except that never re-raises'
