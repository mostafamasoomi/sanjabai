"""Tests for services/smart_router.py -- the live candidate pool, price
bands, rule selection and cost estimate that replace chat_smart.py's
hardcoded model tuples.

WHY THESE TESTS EXECUTE REAL SQL. The default test environment has no
Postgres (tests/conftest.py mocks asyncpg at import time), and the usual
house pattern for a DB-backed query is a fake session that re-implements
the WHERE clause in Python (see tests/test_entitlements.py) plus a separate
literal-text assertion (tests/test_entitlements_sql_contract.py). That pair
cannot catch the failure that matters most here: if someone weakens
`input_per_million > 0` to `IS NOT NULL`, a Python fake keeps enforcing its
own copy of the old rule and stays green while production starts routing
users to unpriced models -- which sort as the cheapest thing in the catalog
and are exactly the loss-making picks the product rule forbids.

So the fake session below runs the module's REAL `sqlalchemy.text()` string
against an in-memory SQLite database seeded with one row per filter this
query has to enforce. Every clause is SQLite-compatible, so the statement
under test is character-for-character the statement production runs, and
deleting any clause from it turns a test red on behaviour rather than on
string matching. The literal-text and no-f-string assertions are kept as
well, because SQLite cannot tell us whether the statement stays visible to
scripts/sql_schema_audit.py.
"""
from __future__ import annotations

import ast
import pathlib
import sqlite3
from types import SimpleNamespace

import pytest

import chat as chat_mod
import services.smart_router as sr


# ── SQLite-backed fake session ───────────────────────────────────────────

_SCHEMA = """
CREATE TABLE model_catalog (
    id TEXT PRIMARY KEY,
    provider_model_id TEXT NOT NULL,
    public_id TEXT,
    availability TEXT NOT NULL,
    input_per_million INTEGER NOT NULL DEFAULT 0,
    output_per_million INTEGER NOT NULL DEFAULT 0,
    context_window INTEGER,
    upstream TEXT,
    health_quarantined_at TEXT
);
CREATE TABLE model_health_state (
    model_id TEXT PRIMARY KEY,
    last_ok_at TEXT
);
"""

# One catalog row per rule the pool query has to enforce. `keep` marks the
# rows that must survive every filter; everything else is a trap, and the
# name says which clause is supposed to catch it.
_CATALOG_ROWS = [
    # id, provider_model_id, public_id, availability, in, out, ctx, upstream, quarantined_at
    ('id-cheap', 'up/cheap', 'sanjab/cheap', 'available', 10_000, 20_000, 128_000, 'bynara', None),
    ('id-mid', 'up/mid', 'sanjab/mid', 'available', 100_000, 200_000, 1_000_000, 'ag', None),
    ('id-high', 'up/high', 'sanjab/high', 'available', 900_000, 900_000, 200_000, 'cc', None),
    # Trap: NUMERIC NOT NULL DEFAULT 0 means "unpriced" reads as 0, and a
    # blended price of 0 sorts ahead of every real model in the catalog.
    ('id-unpriced', 'up/unpriced', 'sanjab/unpriced', 'available', 0, 0, 999_999, 'bynara', None),
    # Trap: only half priced -- one missing side is still unpriced.
    ('id-halfpriced', 'up/halfpriced', 'sanjab/halfpriced', 'available', 5_000, 0, 999_999, 'bynara', None),
    # Trap: no public_id -- serving this would leak a raw provider route.
    ('id-nopublic', 'up/nopublic', None, 'available', 10_000, 10_000, 999_999, 'bynara', None),
    # Trap: quarantined by the health gate.
    ('id-quarantined', 'up/quarantined', 'sanjab/quarantined', 'available', 10_000, 10_000, 999_999, 'bynara', '2026-08-01T00:00:00Z'),
    # Trap: has a health row, but no probe ever succeeded (last_ok_at NULL).
    ('id-unprobed', 'up/unprobed', 'sanjab/unprobed', 'available', 10_000, 10_000, 999_999, 'bynara', None),
    # Trap: never probed at all -- no model_health_state row exists.
    ('id-nohealth', 'up/nohealth', 'sanjab/nohealth', 'available', 10_000, 10_000, 999_999, 'bynara', None),
    # Trap: withdrawn from the catalog.
    ('id-withdrawn', 'up/withdrawn', 'sanjab/withdrawn', 'withdrawn', 10_000, 10_000, 999_999, 'bynara', None),
]

_HEALTH_ROWS = [
    ('id-cheap', '2026-08-27T00:00:00Z'),
    # keyed by provider_model_id rather than id -- the join accepts either.
    ('up/mid', '2026-08-27T00:00:00Z'),
    ('id-high', '2026-08-27T00:00:00Z'),
    ('id-unpriced', '2026-08-27T00:00:00Z'),
    ('id-halfpriced', '2026-08-27T00:00:00Z'),
    ('id-nopublic', '2026-08-27T00:00:00Z'),
    ('id-quarantined', '2026-08-27T00:00:00Z'),
    ('id-unprobed', None),
    ('id-withdrawn', '2026-08-27T00:00:00Z'),
]

# The three rows that pass every filter, cheapest blended first.
_EXPECTED_PUBLIC_IDS = ['sanjab/cheap', 'sanjab/mid', 'sanjab/high']


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SqliteSession:
    """Executes the module's real SQL string against SQLite and hands back
    rows with SQLAlchemy-style attribute access."""

    def __init__(self, conn, calls):
        self._conn = conn
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        self._calls.append(str(stmt))
        cur = self._conn.execute(str(stmt), params or {})
        cols = [d[0] for d in cur.description]
        return _FakeResult([SimpleNamespace(**dict(zip(cols, r))) for r in cur.fetchall()])


class _SessionFactory:
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(_SCHEMA)
        self.conn.executemany(
            'INSERT INTO model_catalog VALUES (?,?,?,?,?,?,?,?,?)', _CATALOG_ROWS)
        self.conn.executemany(
            'INSERT INTO model_health_state VALUES (?,?)', _HEALTH_ROWS)
        self.calls: list[str] = []

    def __call__(self):
        return _SqliteSession(self.conn, self.calls)


class _BoomFactory:
    """A session factory whose query always blows up, for the never-raises
    contract."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        self.calls.append(str(stmt))
        raise RuntimeError('connection reset by peer')


@pytest.fixture(autouse=True)
def _reset_pool_cache():
    """The pool cache is module-level state; leaking it between tests would
    make results depend on test order."""
    sr._pool_cache = []
    sr._pool_cache_at = 0.0
    yield
    sr._pool_cache = []
    sr._pool_cache_at = 0.0


@pytest.fixture
def db(monkeypatch):
    factory = _SessionFactory()
    monkeypatch.setattr(chat_mod, 'async_session', factory)
    return factory


def _cand(public_id, blended, context_window=1000, provider_model_id=None):
    """Hand-built candidate with an exact blended price, for the band and
    selection tests. input/output are back-derived so blended is honest."""
    return sr.Candidate(
        provider_model_id=provider_model_id or f'up/{public_id}',
        public_id=public_id,
        input_per_million=blended // 3,
        output_per_million=blended - 3 * (blended // 3),
        context_window=context_window,
        upstream='bynara',
        blended=blended,
    )


# ── candidate_pool: every filter is load-bearing ─────────────────────────

@pytest.mark.asyncio
async def test_pool_returns_exactly_the_servable_rows(db):
    """The whole filter set at once: any clause dropped from the SQL admits
    one of the trap rows and this set comparison goes red."""
    pool = await sr.candidate_pool()
    assert [c.public_id for c in pool] == _EXPECTED_PUBLIC_IDS


@pytest.mark.asyncio
async def test_pool_excludes_unpriced_model_that_would_sort_cheapest(db):
    """`> 0`, NOT `IS NOT NULL`. The columns are NOT NULL DEFAULT 0, so an
    unpriced row is 0 -- it would become the cheapest candidate in the pool
    and get preferentially routed. No request may be loss-making."""
    pool = await sr.candidate_pool()
    ids = [c.public_id for c in pool]
    assert 'sanjab/unpriced' not in ids
    assert 'sanjab/halfpriced' not in ids
    assert pool[0].public_id == 'sanjab/cheap', 'cheapest real model must lead the pool'
    assert all(c.input_per_million > 0 and c.output_per_million > 0 for c in pool)


@pytest.mark.asyncio
async def test_pool_excludes_models_that_never_answered_a_probe(db):
    """`s.last_ok_at IS NOT NULL`, never `status = 'healthy'` -- _derive_status
    called models healthy whose every probe had failed. A model is offered
    only after a live probe succeeded."""
    ids = [c.public_id for c in await sr.candidate_pool()]
    assert 'sanjab/unprobed' not in ids, 'health row exists but last_ok_at is NULL'
    assert 'sanjab/nohealth' not in ids, 'no health row at all -- the JOIN must drop it'


@pytest.mark.asyncio
async def test_pool_excludes_rows_without_a_public_id(db):
    """A user must never be handed a raw provider route."""
    pool = await sr.candidate_pool()
    ids = [c.public_id for c in pool]
    assert 'None' not in ids and None not in ids
    assert 'up/nopublic' not in [c.provider_model_id for c in pool]


@pytest.mark.asyncio
async def test_pool_excludes_quarantined_rows(db):
    ids = [c.public_id for c in await sr.candidate_pool()]
    assert 'sanjab/quarantined' not in ids


@pytest.mark.asyncio
async def test_pool_excludes_unavailable_rows(db):
    ids = [c.public_id for c in await sr.candidate_pool()]
    assert 'sanjab/withdrawn' not in ids


@pytest.mark.asyncio
async def test_pool_row_fields_and_blended_price(db):
    pool = await sr.candidate_pool()
    cheap = pool[0]
    assert cheap.provider_model_id == 'up/cheap'
    assert cheap.public_id == 'sanjab/cheap'
    assert cheap.input_per_million == 10_000
    assert cheap.output_per_million == 20_000
    assert cheap.context_window == 128_000
    assert cheap.upstream == 'bynara'
    assert cheap.blended == 3 * 10_000 + 20_000 == 50_000
    assert all(isinstance(c.blended, int) for c in pool), 'money is integer Toman only'


@pytest.mark.asyncio
async def test_pool_health_join_matches_on_provider_model_id_too(db):
    """`sanjab/mid`'s health row is keyed by provider_model_id, not id."""
    ids = [c.public_id for c in await sr.candidate_pool()]
    assert 'sanjab/mid' in ids


@pytest.mark.asyncio
async def test_pool_dedupes_a_double_health_match(db):
    """Both keys having a health row must not put the model in the pool
    twice -- a duplicate would skew the band percentiles."""
    db.conn.execute("INSERT INTO model_health_state VALUES ('up/cheap', '2026-08-27T00:00:00Z')")
    pool = await sr.candidate_pool()
    assert [c.public_id for c in pool].count('sanjab/cheap') == 1
    assert [c.public_id for c in pool] == _EXPECTED_PUBLIC_IDS


# ── candidate_pool: caching and the never-raises contract ────────────────

@pytest.mark.asyncio
async def test_pool_is_cached_and_not_requeried_within_ttl(db):
    await sr.candidate_pool()
    await sr.candidate_pool()
    assert len(db.calls) == 1, 'second call inside the TTL must be served from cache'


@pytest.mark.asyncio
async def test_pool_requeries_after_ttl_expires(db):
    await sr.candidate_pool()
    sr._pool_cache_at -= (sr._POOL_CACHE_TTL_SECONDS + 1)
    await sr.candidate_pool()
    assert len(db.calls) == 2


def test_pool_ttl_is_sixty_seconds():
    assert sr._POOL_CACHE_TTL_SECONDS == 60


@pytest.mark.asyncio
async def test_pool_returns_last_good_cache_on_db_error(monkeypatch):
    good = _SessionFactory()
    monkeypatch.setattr(chat_mod, 'async_session', good)
    first = await sr.candidate_pool()
    assert [c.public_id for c in first] == _EXPECTED_PUBLIC_IDS
    boom = _BoomFactory()
    monkeypatch.setattr(chat_mod, 'async_session', boom)
    sr._pool_cache_at -= (sr._POOL_CACHE_TTL_SECONDS + 1)
    again = await sr.candidate_pool()
    assert boom.calls, 'the failing query must actually have been attempted'
    assert [c.public_id for c in again] == _EXPECTED_PUBLIC_IDS


@pytest.mark.asyncio
async def test_pool_returns_empty_list_on_cold_db_error(monkeypatch):
    monkeypatch.setattr(chat_mod, 'async_session', _BoomFactory())
    assert await sr.candidate_pool() == []


@pytest.mark.asyncio
async def test_pool_returns_empty_list_when_no_session(monkeypatch):
    """Warm the cache first: with a cold cache `return []` and
    `return _pool_cache` are indistinguishable, and the contract is the
    former -- no session means no pool, whatever was cached."""
    monkeypatch.setattr(chat_mod, 'async_session', _SessionFactory())
    assert [c.public_id for c in await sr.candidate_pool()] == _EXPECTED_PUBLIC_IDS
    monkeypatch.setattr(chat_mod, 'async_session', None)
    assert await sr.candidate_pool() == []


# ── SQL shape guards the SQLite run cannot cover ─────────────────────────

_SRC_PATH = pathlib.Path(sr.__file__)
_SRC = _SRC_PATH.read_text()


def test_pool_sql_is_a_plain_string_literal():
    """scripts/sql_schema_audit.py only EXPLAINs literal text() arguments;
    an f-string or a joined variable silently drops this query out of the
    audit and a wrong column name then survives to production."""
    tree = ast.parse(_SRC)
    literal_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr != 'text':
            continue
        if 'sqlalchemy' not in ast.unparse(f.value):
            continue
        arg = node.args[0]
        assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (
            f'sqlalchemy.text() argument at line {node.lineno} is not a plain '
            f'string literal ({type(arg).__name__}) -- the SQL audit will skip it'
        )
        literal_calls += 1
    assert literal_calls == 1, f'expected exactly one text() call, found {literal_calls}'


def test_pool_sql_keeps_every_load_bearing_clause():
    sql = str(sr._POOL_SQL)
    for clause in (
        "c.availability = 'available'",
        'c.public_id IS NOT NULL',
        'c.input_per_million > 0',
        'c.output_per_million > 0',
        'c.health_quarantined_at IS NULL',
        's.last_ok_at IS NOT NULL',
    ):
        assert clause in sql, f'pool SQL lost its {clause!r} filter'
    for weakened in ('c.input_per_million IS NOT NULL', 'c.output_per_million IS NOT NULL'):
        assert weakened not in sql, (
            'per-million columns must be filtered with > 0, not IS NOT NULL -- '
            'they are NOT NULL DEFAULT 0, so unpriced reads as the cheapest model'
        )
    assert "status = 'healthy'" not in sql, 'status lies; only last_ok_at is trustworthy'
    assert 'last_verified_at' not in sql, 'last_verified_at is known-unreliable'


def test_router_does_not_read_package_entitlements():
    """Owner decision, explicit and not re-opened: holding an active credit
    package does NOT earn a better band. Balance alone gates.

    Checked over the AST rather than the raw text, so the comment in
    smart_router.py that explains this decision doesn't trip it -- only real
    imports and real name/attribute references count."""
    tree = ast.parse(_SRC)
    forbidden = {'has_active_package', 'user_quota', 'premium_quota', 'entitlement_gate'}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name.split('.')[-1] in forbidden]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or '').split('.')[-1] in forbidden:
                hits.append(node.module)
            hits += [a.name for a in node.names if a.name in forbidden]
        elif isinstance(node, ast.Name) and node.id in forbidden:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in forbidden:
            hits.append(node.attr)
    assert not hits, f'smart_router must not consult package entitlements, found {hits}'


def test_module_stays_under_the_five_hundred_line_cap():
    assert len(_SRC.splitlines()) < 500


# ── Bands: by price VALUE, never by row count ────────────────────────────

# Nine prices with a tie sitting on each count-based boundary: ntile(3) over
# nine rows cuts after index 2 and index 5, which splits the 300 pair and
# the 500 pair. Value thresholds must keep each pair together.
_TIE_PRICES = [100, 200, 300, 300, 400, 500, 500, 700, 800]

# The two candidates that change band between the value scheme and the
# positional one get a huge context window, so `select_by_rules` -- which
# picks the biggest context window in the band -- returns a different model
# under each scheme. Without this, a positional re-implementation inside
# select_by_rules would slip past the band_of/band_thresholds tests, which
# never call it.
_TIE_CONTEXT = {3: 900_000, 6: 800_000}


def _tie_pool():
    return [
        _cand(f'm{i:02d}', p, context_window=_TIE_CONTEXT.get(i, 10_000 + i))
        for i, p in enumerate(_TIE_PRICES)
    ]


def test_thresholds_are_percentile_values_from_the_pool():
    assert sr.band_thresholds(_tie_pool()) == (300, 500)


def test_equal_prices_straddling_the_lower_count_boundary_share_a_band():
    """The subtle one. Under ntile(3) the two 300s land at indices 2 and 3 --
    different bands, decided by nothing but row order, so an unrelated
    catalog insert silently re-bands a model. Value thresholds must not."""
    pool = _tie_pool()
    th = sr.band_thresholds(pool)
    tied = [c for c in pool if c.blended == 300]
    assert len(tied) == 2
    bands = {sr.band_of(c, th) for c in tied}
    assert bands == {1}, f'the 300 tie was split across bands {bands}'


def test_equal_prices_straddling_the_upper_count_boundary_share_a_band():
    pool = _tie_pool()
    th = sr.band_thresholds(pool)
    tied = [c for c in pool if c.blended == 500]
    assert len(tied) == 2
    bands = {sr.band_of(c, th) for c in tied}
    assert bands == {2}, f'the 500 tie was split across bands {bands}'


def test_band_membership_is_by_value_not_by_equal_counts():
    pool = _tie_pool()
    th = sr.band_thresholds(pool)
    by_band = {}
    for c in pool:
        by_band.setdefault(sr.band_of(c, th), []).append(c.blended)
    assert by_band[1] == [100, 200, 300, 300]
    assert by_band[2] == [400, 500, 500]
    assert by_band[3] == [700, 800]


def test_bands_on_the_live_price_distribution():
    """The 26 blended prices measured on the live catalog on 2026-08-27,
    including the three-way tie at 2,573,100 that ntile(3) split."""
    live = [
        49_556, 91_170, 104_830, 121_984, 133_420, 176_114, 333_550, 428_850,
        428_850, 552_740, 648_040, 648_040, 1_143_600, 1_524_800, 1_639_160,
        2_287_200, 2_573_100, 2_573_100, 2_573_100, 3_430_800, 4_574_400,
        4_574_400, 7_624_000, 7_624_000, 7_624_000, 15_248_000,
    ]
    pool = [_cand(f'live{i:02d}', p) for i, p in enumerate(live)]
    th = sr.band_thresholds(pool)
    assert th == (428_850, 2_573_100)
    for price in (428_850, 2_573_100, 7_624_000, 648_040):
        bands = {sr.band_of(c, th) for c in pool if c.blended == price}
        assert len(bands) == 1, f'price {price} was split across bands {bands}'


def test_selection_uses_value_bands_not_positional_thirds():
    """The same tie, checked through `select_by_rules` -- band_of and
    band_thresholds cannot catch a positional re-implementation inside the
    selector, because the selector is free to band by row position without
    ever calling them.

    Nine prices, ntile(3) cuts after index 2 and index 5:
      value bands  -> 1: m00 m01 m02 m03 | 2: m04 m05 m06 | 3: m07 m08
      ntile bands  -> 1: m00 m01 m02     | 2: m03 m04 m05 | 3: m06 m07 m08
    m03 (the second 300) and m06 (the second 500) hold the two largest
    context windows, so a positional scheme answers m02 for `simple` and
    m03 for `code` instead of m03 and m06."""
    pool = _tie_pool()
    assert sr.select_by_rules('simple', 500_000, pool).public_id == 'm03'
    assert sr.select_by_rules('code', 500_000, pool).public_id == 'm06'


def test_band_of_boundaries_are_inclusive():
    th = (300, 500)
    assert sr.band_of(_cand('a', 299), th) == 1
    assert sr.band_of(_cand('b', 300), th) == 1
    assert sr.band_of(_cand('c', 301), th) == 2
    assert sr.band_of(_cand('d', 500), th) == 2
    assert sr.band_of(_cand('e', 501), th) == 3


def test_thresholds_of_empty_and_single_pools():
    assert sr.band_thresholds([]) == (0, 0)
    single = [_cand('only', 777)]
    assert sr.band_thresholds(single) == (777, 777)
    assert sr.band_of(single[0], sr.band_thresholds(single)) == 1


def test_thresholds_are_integers():
    th = sr.band_thresholds(_tie_pool())
    assert all(isinstance(v, int) and not isinstance(v, bool) for v in th)


# ── select_by_rules ──────────────────────────────────────────────────────

def _rules_pool():
    """One candidate per band, plus a same-band pair for the tie-break."""
    return [
        _cand('sanjab/cheap-a', 100, context_window=8_000),
        _cand('sanjab/cheap-b', 100, context_window=128_000),
        _cand('sanjab/mid', 400, context_window=32_000),
        _cand('sanjab/high', 900, context_window=32_000),
    ]


def test_low_balance_forces_the_cheap_band_whatever_the_category():
    """Today's behaviour, confirmed by the owner: under 10,000 Toman the
    user gets band 1 no matter what they asked for."""
    pool = _rules_pool()
    for category in ('greeting', 'simple', 'medium', 'code', 'creative', 'reasoning', 'complex', 'weird'):
        pick = sr.select_by_rules(category, 9_999, pool)
        assert pick is not None
        assert sr.band_of(pick, sr.band_thresholds(pool)) == 1, (
            f'category {category} escaped the low-balance floor with {pick.public_id}'
        )


def test_low_balance_gets_the_cheapest_in_band_not_the_roomiest():
    """Under the floor, price beats context window.

    `_rules_pool` puts 'sanjab/cheap-a' (8k context) and 'sanjab/cheap-b'
    (128k) in band 1 at the same blended price, so that pair alone cannot
    show this -- the extra cheaper-but-smaller row below can. Band 1 spans
    a real spread in production (measured live: 49,556 to 428,850 blended),
    and the normal `_best_in` rule of "roomiest in band" would hand the
    near-empty wallet the priciest model in the band. Today's production
    behaviour for balance < 10,000 is the cheapest model outright; this
    keeps that promise to exactly the users who can least absorb losing it.

    A funded user is unaffected -- see the assertion at the end.
    """
    pool = _rules_pool() + [_cand('sanjab/cheapest', 10, context_window=4_000)]
    pick = sr.select_by_rules('greeting', 9_999, pool)
    assert pick.public_id == 'sanjab/cheapest', (
        f'low-balance user got {pick.public_id} instead of the cheapest model'
    )
    # And the funded path still prefers the roomiest model in its band.
    assert sr.select_by_rules('greeting', 10_000, pool).public_id == 'sanjab/cheap-b'


def test_balance_floor_boundary_is_exactly_ten_thousand():
    pool = _rules_pool()
    th = sr.band_thresholds(pool)
    assert sr.band_of(sr.select_by_rules('reasoning', 9_999, pool), th) == 1
    assert sr.band_of(sr.select_by_rules('reasoning', 10_000, pool), th) == 3


def test_category_to_band_mapping_for_a_funded_user():
    pool = _rules_pool()
    th = sr.band_thresholds(pool)
    expected = {
        'greeting': 1, 'simple': 1, 'medium': 1,
        'code': 2, 'creative': 2,
        'reasoning': 3, 'complex': 3,
        'nonsense-category': 1, '': 1,
    }
    for category, band in expected.items():
        pick = sr.select_by_rules(category, 500_000, pool)
        assert pick is not None
        assert sr.band_of(pick, th) == band, (
            f'category {category} should land in band {band}, got {pick.public_id}'
        )


def test_within_band_the_largest_context_window_wins():
    """Both cheap candidates are in band 1 at the same price; the pick is
    the one with the bigger context window, not the first row."""
    pool = _rules_pool()
    pick = sr.select_by_rules('simple', 500_000, pool)
    assert pick.public_id == 'sanjab/cheap-b'
    assert pick.context_window == 128_000


def test_within_band_ties_break_on_public_id_ascending():
    pool = [
        _cand('sanjab/zeta', 100, context_window=64_000),
        _cand('sanjab/alpha', 100, context_window=64_000),
        _cand('sanjab/beta', 100, context_window=64_000),
    ]
    assert sr.select_by_rules('simple', 500_000, pool).public_id == 'sanjab/alpha'


def test_selection_is_deterministic_across_pool_orderings():
    pool = _rules_pool()
    first = sr.select_by_rules('simple', 500_000, pool).public_id
    for shifted in (pool[1:] + pool[:1], list(reversed(pool))):
        assert sr.select_by_rules('simple', 500_000, shifted).public_id == first


def test_empty_band_falls_back_to_the_next_cheaper_band():
    """All three prices equal -> p33 == p67 == max, so bands 2 and 3 are
    empty and a band-3 category must walk down to band 1 rather than fail."""
    flat = [_cand('sanjab/x', 100, context_window=1_000),
            _cand('sanjab/y', 100, context_window=9_000),
            _cand('sanjab/z', 100, context_window=5_000)]
    th = sr.band_thresholds(flat)
    assert {sr.band_of(c, th) for c in flat} == {1}
    pick = sr.select_by_rules('reasoning', 500_000, flat)
    assert pick is not None and pick.public_id == 'sanjab/y'


def test_fallback_goes_down_a_band_never_up():
    """Band 3 empty (top price equals p67) -> a reasoning request settles
    for band 2, not for something more expensive."""
    pool = [_cand('sanjab/one', 100), _cand('sanjab/two', 200), _cand('sanjab/three', 200)]
    th = sr.band_thresholds(pool)
    assert th == (100, 200)
    assert not [c for c in pool if sr.band_of(c, th) == 3]
    pick = sr.select_by_rules('reasoning', 500_000, pool)
    assert sr.band_of(pick, th) == 2


def test_empty_pool_returns_none():
    assert sr.select_by_rules('code', 500_000, []) is None
    assert sr.select_by_rules('code', 0, []) is None


def test_select_by_rules_never_raises_on_broken_input():
    """Contract: never raises. A caller in the chat path must always get an
    answer it can fall back from, not an exception mid-request."""
    assert sr.select_by_rules('code', 500_000, [object()]) is None


# ── estimate_cost_toman ──────────────────────────────────────────────────

def test_estimate_uses_integer_toman_arithmetic():
    c = sr.Candidate(
        provider_model_id='up/priced', public_id='sanjab/priced',
        input_per_million=500_000, output_per_million=1_000_000,
        context_window=1_000, upstream='bynara',
        blended=3 * 500_000 + 1_000_000,
    )
    cost = sr.estimate_cost_toman(c)
    # (2000 * 500000 + 800 * 1000000) // 1_000_000
    assert cost == 1_800
    assert isinstance(cost, int) and not isinstance(cost, bool)


def test_estimate_is_floored_so_nothing_ever_looks_free():
    """There are no free models on this platform; a rounding-down estimate
    of 0 would read as one."""
    c = sr.Candidate(
        provider_model_id='up/tiny', public_id='sanjab/tiny',
        input_per_million=1, output_per_million=1,
        context_window=1_000, upstream=None, blended=4,
    )
    assert sr.estimate_cost_toman(c) == 1_000


def test_estimate_never_produces_a_float():
    for price in (1, 999, 49_556, 15_248_000, 7):
        c = sr.Candidate(
            provider_model_id='up/x', public_id='sanjab/x',
            input_per_million=price, output_per_million=price,
            context_window=1, upstream=None, blended=4 * price,
        )
        assert type(sr.estimate_cost_toman(c)) is int


@pytest.mark.asyncio
async def test_estimate_works_on_a_real_pool_row(db):
    pool = await sr.candidate_pool()
    costs = [sr.estimate_cost_toman(c) for c in pool]
    assert costs == sorted(costs), 'a cheaper blended price must not estimate higher here'
    assert all(type(x) is int and x >= 1_000 for x in costs)


# ── end-to-end over the real SQL ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_pool_to_selection_end_to_end(db):
    pool = await sr.candidate_pool()
    assert sr.select_by_rules('simple', 500_000, pool).public_id == 'sanjab/cheap'
    assert sr.select_by_rules('code', 500_000, pool).public_id == 'sanjab/mid'
    assert sr.select_by_rules('reasoning', 500_000, pool).public_id == 'sanjab/high'
    assert sr.select_by_rules('reasoning', 0, pool).public_id == 'sanjab/cheap'
