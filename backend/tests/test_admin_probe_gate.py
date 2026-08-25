"""Probe gate (services/probe_gate.py) unit tests, plus wiring into the two
admin decision points that can put a model ON SALE:
`admin_catalog.bulk_set_availability` and `admin_pricing.toggle_model`.
Also covers the two smaller findings from the same audit: the markup_pct
upper cap (admin_catalog._parse_markup_pct) and org-default-model
validation (admin_content.set_org_default_model).

Honest-labelling rule: «مدل فقط بعد از پروب زنده موفق به کاربر ارائه می‌شود».
Before this module nothing on the server enforced it -- see
services/probe_gate.py's module docstring for why the check is against
`model_health_state.last_ok_at`, never `model_catalog.last_verified_at`
(that column is NOT NULL DEFAULT now(), so an unprobed row still carries
today's date).

Style mirrors tests/test_margin_guard.py throughout: a hand-rolled async
session double for the pure-function unit tests, and endpoint-level wiring
tests that patch the sibling guard (margin / probe) out so each guard is
exercised in isolation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import probe_gate as probe_gate_mod
from tests.conftest import make_result, make_row


# ── Unit tests: services.probe_gate.refuse_if_unprobed ──────────────────

class _Session:
    """Async session double that records SQL and replays queued rows --
    same shape as test_margin_guard.py's `_Session` double."""

    def __init__(self, rows, raises=False):
        self.rows = rows
        self.raises = raises
        self.sql = []

    async def execute(self, stmt, params=None, *a, **k):
        self.sql.append(str(stmt))
        if self.raises:
            raise RuntimeError('database is on fire')
        return make_result(fetchall=self.rows)


def _confirmed(model_id):
    """One row of what the gate's query returns: a catalog id that JOINed to
    a model_health_state row with a non-NULL last_ok_at.

    The NULL filtering moved into SQL when the query grew a join onto
    model_catalog (health samples are keyed by `provider_model_id` for the
    background sweep and by catalog `id` for the admin's «تست زنده», and
    matching only one of them refused models that had in fact been probed).
    So the double no longer replays last_ok_at at all -- a model that was
    never confirmed simply does not come back, which is what
    test_last_ok_at_null_is_filtered_in_sql pins down."""
    return make_row(catalog_id=model_id)


@pytest.mark.anyio
class TestRefuseIfUnprobed:
    @pytest.fixture
    def anyio_backend(self):
        return 'asyncio'

    async def test_all_confirmed_is_allowed(self):
        session = _Session([_confirmed('m1'), _confirmed('m2')])
        assert await probe_gate_mod.refuse_if_unprobed(session, ['m1', 'm2']) is None

    async def test_last_ok_at_null_is_filtered_in_sql(self):
        """The "row exists but was never confirmed working" case is now
        excluded by the query itself, so assert the query says so. Without
        this predicate the join would confirm any model that merely HAS a
        health row -- including one whose every probe has failed."""
        session = _Session([])
        await probe_gate_mod.refuse_if_unprobed(session, ['m1'])
        assert 'last_ok_at IS NOT NULL' in session.sql[0]

    async def test_the_query_matches_either_id_column(self):
        """The background sweep records under provider_model_id, «تست زنده»
        under the catalog id. Matching only one of them refuses a model that
        was in fact probed successfully."""
        session = _Session([])
        await probe_gate_mod.refuse_if_unprobed(session, ['m1'])
        assert 's.model_id = c.id' in session.sql[0]
        assert 's.model_id = c.provider_model_id' in session.sql[0]

    async def test_one_with_no_confirmed_probe_is_refused(self):
        """m2 never appears in the query result -- whether because it has no
        model_health_state row at all or because its last_ok_at is NULL, both
        are the same "never confirmed working" case."""
        session = _Session([_confirmed('m1')])
        refusal = await probe_gate_mod.refuse_if_unprobed(session, ['m1', 'm2'])
        assert refusal is not None
        assert 'm2' in refusal.detail
        assert refusal.audit['unprobed_ids'] == ['m2']

    async def test_confirmed_ids_are_never_named_in_the_refusal(self):
        session = _Session([_confirmed('m1')])
        refusal = await probe_gate_mod.refuse_if_unprobed(session, ['m1', 'm2'])
        assert 'm1' not in refusal.detail

    async def test_empty_id_list_short_circuits_without_a_query(self):
        session = _Session([])
        assert await probe_gate_mod.refuse_if_unprobed(session, []) is None
        assert session.sql == []

    async def test_a_failing_query_refuses_rather_than_waving_through(self):
        """Fail closed: if the guard cannot prove every id was probed, it
        must not default to permissive. Never raises on the caller."""
        session = _Session([], raises=True)
        refusal = await probe_gate_mod.refuse_if_unprobed(session, ['m1'])
        assert refusal is not None
        assert 'پروب' in refusal.detail or 'بررسی' in refusal.detail

    async def test_more_than_five_offenders_are_capped_with_a_count(self):
        ids = [f'm{i}' for i in range(8)]
        session = _Session([])  # none confirmed
        refusal = await probe_gate_mod.refuse_if_unprobed(session, ids)
        assert refusal is not None
        assert 'و 3 مدل دیگر' in refusal.detail
        assert refusal.audit['unprobed_count'] == 8

    async def test_duplicate_ids_are_reported_once(self):
        session = _Session([])
        refusal = await probe_gate_mod.refuse_if_unprobed(session, ['dup', 'dup', 'dup'])
        assert refusal is not None
        assert refusal.detail.count('dup') == 1
        assert refusal.audit['unprobed_count'] == 1

    async def test_detail_text_is_persian(self):
        session = _Session([])
        refusal = await probe_gate_mod.refuse_if_unprobed(session, ['m1'])
        assert 'تست زنده' in refusal.detail


# ── Wiring: the two decision points that can put a model on sale ────────

import admin_catalog as admin_catalog_mod  # noqa: E402
import admin_content as admin_content_mod  # noqa: E402
import admin_pricing as admin_pricing_mod  # noqa: E402
from services import margin as margin_mod  # noqa: E402


@pytest.fixture
def admin_ok():
    with patch('admin_catalog.admin_required', new=AsyncMock(return_value=True)), \
         patch('admin.admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def margin_allows():
    """Isolate the probe gate: the margin guard always says yes."""
    with patch.object(margin_mod, 'refuse_if_loss_making', new=AsyncMock(return_value=None)):
        yield


@pytest.fixture
def probe_allows():
    """Isolate the margin guard: the probe gate always says yes. Records
    the ids each call site actually passed it."""
    calls = []

    async def _guard(session, ids):
        calls.append(list(ids))
        return None

    with patch.object(probe_gate_mod, 'refuse_if_unprobed', new=_guard):
        yield calls


@pytest.fixture
def probe_refuses():
    refusal = probe_gate_mod.ProbeRefusal(
        detail=(
            'این مدل‌ها هنوز پروب زنده موفق ندارند و قابل فعال‌سازی نیستند: «m1». '
            'مدل فقط بعد از پروب زنده موفق به کاربر ارائه می‌شود -- ابتدا «تست زنده» '
            'را روی این مدل‌ها اجرا کنید.'
        ),
        audit={'model_count': 1, 'unprobed_count': 1, 'unprobed_ids': ['m1'],
               'reason': 'no confirmed live probe (model_health_state.last_ok_at IS NULL or no row)'},
    )
    calls = []

    async def _guard(session, ids):
        calls.append(list(ids))
        return refusal

    with patch.object(probe_gate_mod, 'refuse_if_unprobed', new=_guard):
        yield calls


@pytest.fixture
def rowcount_1(mock_async_session):
    """Every UPDATE/SELECT in these endpoints reports one affected row and
    an 'available'-flippable stored state -- same shape as
    test_margin_guard.py's `rowcount_1` fixture."""
    executed = []

    async def _execute(stmt, params=None, *a, **k):
        executed.append((str(stmt), params))
        result = make_result(fetchone=make_row(availability='disabled'))
        result.rowcount = 1
        return result

    mock_async_session.execute = _execute
    mock_async_session._executed = executed
    return mock_async_session


def _updates(session):
    return [sql for sql, _ in session._executed if 'UPDATE model_catalog' in sql]


class TestBulkAvailabilityIsProbeGated:
    """POST /admin/models/bulk-availability."""

    def test_bulk_enable_is_refused_when_probe_gate_refuses(
        self, client, admin_ok, rowcount_1, margin_allows, probe_refuses,
    ):
        resp = client.post('/admin/models/bulk-availability',
                            json={'ids': ['m1'], 'availability': 'available'})
        assert resp.status_code == 400
        assert 'پروب زنده' in resp.json()['detail']
        assert not _updates(rowcount_1)

    def test_bulk_enable_is_allowed_when_every_id_is_probe_confirmed(
        self, client, admin_ok, rowcount_1, margin_allows, probe_allows,
    ):
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/bulk-availability',
                                json={'ids': ['m1', 'm2'], 'availability': 'available'})
        assert resp.status_code == 200
        assert _updates(rowcount_1)
        assert probe_allows == [['m1', 'm2']]

    def test_bulk_disable_is_allowed_even_for_unprobed_models(
        self, client, admin_ok, rowcount_1, probe_refuses,
    ):
        """Withdrawal is never a correctness risk -- must not be gated,
        even when every id in the batch has never been probed."""
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/bulk-availability',
                                json={'ids': ['m1'], 'availability': 'disabled'})
        assert resp.status_code == 200
        assert probe_refuses == []  # the guard was never even consulted
        assert _updates(rowcount_1)

    def test_refusal_is_audited(self, client, admin_ok, rowcount_1, margin_allows, probe_refuses):
        with patch.object(admin_catalog_mod, '_write_audit_log', new=AsyncMock()) as audit:
            client.post('/admin/models/bulk-availability',
                        json={'ids': ['m1'], 'availability': 'available'})
        audit.assert_awaited()
        assert audit.await_args.args[0] == 'admin.model.probe_refused'


class TestToggleModelIsProbeGated:
    """POST /admin/models/{id}/toggle."""

    def test_toggle_to_available_is_refused_when_unprobed(
        self, client, admin_ok, rowcount_1, margin_allows, probe_refuses,
    ):
        resp = client.post('/admin/models/some/model/toggle')
        assert resp.status_code == 400
        assert 'پروب زنده' in resp.json()['detail']
        assert not _updates(rowcount_1)

    def test_toggle_to_available_succeeds_when_probe_confirmed(
        self, client, admin_ok, rowcount_1, margin_allows, probe_allows,
    ):
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/some/model/toggle')
        assert resp.status_code == 200
        assert resp.json()['availability'] == 'available'

    def test_toggle_to_disabled_is_never_probe_gated(
        self, client, admin_ok, mock_async_session, probe_refuses,
    ):
        """available -> disabled is a withdrawal; must not be blocked even
        though the probe guard (patched to always refuse here) would."""
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        mock_async_session._execute_result.rowcount = 1
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/some/model/toggle')
        assert resp.status_code == 200
        assert resp.json()['availability'] == 'disabled'
        assert probe_refuses == []

    def test_refusal_is_audited(self, client, admin_ok, rowcount_1, margin_allows, probe_refuses):
        with patch.object(admin_pricing_mod, '_write_audit_log', new=AsyncMock()) as audit:
            client.post('/admin/models/some/model/toggle')
        audit.assert_awaited()
        assert audit.await_args.args[0] == 'admin.model.probe_refused'


# ── markup_pct upper cap (admin_catalog._parse_markup_pct) ──────────────

class TestMarkupPctUpperCap:
    """700 typed instead of 7 used to be silently accepted and multiply
    every price on that model ~8x -- see admin_catalog.py's comment on
    `_MARKUP_PCT_MAX` for why 1000 (10x) was chosen."""

    def test_above_cap_is_rejected(self):
        pct, err = admin_catalog_mod._parse_markup_pct(1000.01, allow_null=False)
        assert pct is None
        assert err is not None and 'سقف' in err

    def test_at_the_cap_is_accepted(self):
        pct, err = admin_catalog_mod._parse_markup_pct(1000, allow_null=False)
        assert pct == 1000
        assert err is None

    def test_ordinary_value_is_still_accepted(self):
        pct, err = admin_catalog_mod._parse_markup_pct(7, allow_null=False)
        assert pct == 7
        assert err is None

    def test_endpoint_rejects_above_cap(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/markup/global', json={'markup_pct': 5000})
        assert resp.status_code == 400
        assert 'سقف' in resp.json()['detail']

    def test_endpoint_accepts_at_cap(self, client, admin_ok, mock_async_session):
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/markup/global', json={'markup_pct': 1000})
        assert resp.status_code == 200


# ── org-default-model validation (admin_content.set_org_default_model) ──

class TestOrgDefaultModelValidation:
    """POST /admin/org-default-model used to write `default_model`
    verbatim with no check it names a real, available model."""

    def test_empty_string_stays_legal(self, client, admin_ok, mock_async_session):
        """The frontend uses '' explicitly to mean "no default, use the
        first model in the list" -- must not be forced through the
        model_catalog lookup."""
        with patch.object(admin_content_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/org-default-model', json={'default_model': ''})
        assert resp.status_code == 200
        assert resp.json()['default_model'] == ''

    def test_nonexistent_model_is_rejected(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = client.post('/admin/org-default-model', json={'default_model': 'nope/nope'})
        assert resp.status_code == 400
        assert 'یافت نشد' in resp.json()['detail']

    def test_unavailable_model_is_rejected(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='maintenance'))
        resp = client.post('/admin/org-default-model', json={'default_model': 'some/model'})
        assert resp.status_code == 400
        assert 'فعال نیست' in resp.json()['detail']

    def test_available_model_is_accepted(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        with patch.object(admin_content_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/org-default-model', json={'default_model': 'some/model'})
        assert resp.status_code == 200
        assert resp.json()['default_model'] == 'some/model'

    def test_rejected_model_never_reaches_the_database_write(self, client, admin_ok, mock_async_session):
        executed = []

        async def _execute(stmt, params=None, *a, **k):
            executed.append(str(stmt))
            return make_result(fetchone=None)

        mock_async_session.execute = _execute
        client.post('/admin/org-default-model', json={'default_model': 'nope/nope'})
        assert not any('proxy_config' in sql.lower() for sql in executed)
