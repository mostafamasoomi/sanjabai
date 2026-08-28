"""Tests for the moderation + free-tier + quota + billing gates added to
backend/services/rag.py::query_documents.

Before this fix, POST /v1/rag/query reached `{LITELLM_HOST}/v1/chat/
completions` with ZERO content screening, ZERO free-tier/quota gating, and
ZERO billing on the completion call itself (`grep -iE 'moderation|
free_tier|check_and_consume|user_quota|reserve\\(|billing|Money|settle'
rag_endpoints.py services/rag.py` was empty at HEAD). Only the query
EMBEDDING was billed, separately, via services/embeddings.py's usage_events
write -- untouched here, not duplicated.

Mocking style mirrors tests/test_task_execution_gates.py:
services.rag.query_documents is called directly, exactly like
task_execution._execute_task -- it returns a plain dict, never an HTTP
response, so there is no JSONResponse to parse. `Verdict` is the real
dataclass from services/moderation_rules.py, so these tests pin the actual
contract screen_request returns, not a hand-rolled guess.

The companion images.py moderation-gate tests live in
tests/test_rag_image_gates.py -- split out purely to keep both files under
the house 500-line cap.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import services.moderation as moderation_mod
import services.rag as rag_mod
from services.moderation_rules import Verdict

_BLOCK_MESSAGE = (
    'این درخواست با قوانین محتوایی سنجاب همخوانی ندارد و ارسال نشد. '
    'لطفاً پیام را به‌گونه‌ای دیگر بازنویسی کنید.'
)


def _fake_row(*, content='سیاست بازگشت کالا تا ده روز پس از خرید امکان‌پذیر است.',
              similarity=0.9, file_name='doc.txt', title='', chunk_index=0):
    row = MagicMock()
    row._mapping = {
        'content': content,
        'chunk_index': chunk_index,
        'title': title,
        'file_name': file_name,
        'similarity': similarity,
    }
    return row


def _rag_fake_async_session():
    """`async with async_session() as session:` -- `session.execute` is a
    REAL AsyncMock whose result's `.fetchall()` returns `[]` by default, so
    query_documents' pgvector fallback branch (entered whenever keyword
    search comes back empty -- see "2b. Semantic (or keyword empty)" in
    query_documents) runs its genuine "no rows" code path.

    Previously this session's `.execute` was a plain (non-awaitable)
    MagicMock: `await session.execute(...)` raised "object MagicMock can't
    be used in 'await' expression", which query_documents' own
    `except Exception` around that call swallowed and logged as "Vector
    search failed" -- silently turning the "zero chunks retrieved" test
    into an accidental exception test that happened to produce a
    superficially similar-looking (but different) Persian error string.
    Fixed by making `.execute` a real AsyncMock returning a result object
    whose `.fetchall()` is a plain (sync) callable, matching SQLAlchemy's
    actual `Result.fetchall()` shape (sync method on an awaited result).

    BillingService is always mocked out separately (see _rag_billing_mock),
    so the only other thing ever awaited on this session is `.commit()`."""
    class _Ctx:
        async def __aenter__(self):
            session = MagicMock()
            session.commit = AsyncMock(return_value=None)
            result = MagicMock()
            result.fetchall = MagicMock(return_value=[])
            session.execute = AsyncMock(return_value=result)
            return session

        async def __aexit__(self, *a):
            return None

    return MagicMock(return_value=_Ctx())


def _rag_billing_mock(reserve_result=None):
    instance = MagicMock()
    instance.reserve = AsyncMock(
        return_value=reserve_result or {'reservation_id': 'rag-resv-1', 'hold_amount': 1000}
    )
    instance.release = AsyncMock(return_value=None)
    instance.settle = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


def _rag_upstream_response(status_code=200, body=None, text=''):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body if body is not None else {
        'choices': [{'message': {'content': 'پاسخ نمونه بر اساس سند'}}],
        'usage': {'prompt_tokens': 50, 'completion_tokens': 30, 'total_tokens': 80},
    })
    resp.text = text
    return resp


class _RagPatches:
    """Bundles every patch a single `query_documents` call needs. Defaults
    are the happy path -- chat enabled, moderation allows, both gates pass,
    keyword search returns one relevant chunk, reserve/upstream/bill all
    succeed -- so each test only overrides what it is specifically
    exercising. Hash-mode keyword search is forced on (`_embedding_is_hash`
    -> True) so retrieval normally never touches the real pgvector branch;
    `rows=[]` is the one case that does (see _rag_fake_async_session)."""

    def __init__(self, *, chat_enabled=True, verdict=None, ft_gate=None, q_gate=None,
                 reserve_result=None, http_post=None, bill_result=None,
                 resolved_model='bynara/mimo-v2.5', rows=None):
        self.async_session = _rag_fake_async_session()
        self.billing_cls, self.billing_instance = _rag_billing_mock(reserve_result)
        self.fake_http = MagicMock()
        self.fake_http.post = http_post or AsyncMock(return_value=_rag_upstream_response())
        self.verdict = verdict if verdict is not None else Verdict(decision='allow')
        self._chat_enabled = chat_enabled
        self.ft_gate = ft_gate
        self.q_gate = q_gate
        self.resolved_model = resolved_model
        self.rows = rows if rows is not None else [_fake_row()]
        self.bill_result = bill_result or {
            'cost': 77, 'input_tokens': 50, 'output_tokens': 30, 'balance_after': 500,
        }
        self.release_spy = AsyncMock(return_value=None)

    def __enter__(self):
        self.get_site_flag = AsyncMock(return_value=self._chat_enabled)
        self.screen_request = AsyncMock(return_value=self.verdict)
        self.free_tier_check = AsyncMock(return_value=self.ft_gate)
        self.user_quota_check = AsyncMock(return_value=self.q_gate)
        # Neither an entitlement nor the free tier covers this request by
        # default -- the normal wallet reservation path, matching every
        # test below written before these two gates existed at this call
        # site.
        self.covering_entitlement = AsyncMock(return_value=None)
        self.covers_request = AsyncMock(return_value=False)
        self.embed_single = AsyncMock(return_value=[0.1, 0.2, 0.3])
        self.keyword_search = AsyncMock(return_value=self.rows)
        self.embedding_is_hash = MagicMock(return_value=True)
        self.bill_mock = AsyncMock(return_value=self.bill_result)
        self._patches = [
            patch.object(rag_mod, 'async_session', self.async_session),
            patch.object(rag_mod, '_http', self.fake_http),
            patch.object(rag_mod, 'BillingService', self.billing_cls),
            patch.object(rag_mod, 'get_site_flag', self.get_site_flag),
            patch.object(rag_mod, 'screen_request', self.screen_request),
            patch.object(rag_mod, '_free_tier_check', self.free_tier_check),
            patch.object(rag_mod, '_user_quota_check', self.user_quota_check),
            patch.object(rag_mod, 'covering_entitlement', self.covering_entitlement),
            patch.object(rag_mod, 'covers_request', self.covers_request),
            patch.object(rag_mod, 'embed_single', self.embed_single),
            patch.object(rag_mod, '_keyword_search', self.keyword_search),
            patch.object(rag_mod, '_embedding_is_hash', self.embedding_is_hash),
            patch.object(rag_mod, '_release_reservation', self.release_spy),
            patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: self.resolved_model)),
            patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)),
            patch.object(chat_mod, '_bill_stream_usage', self.bill_mock),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


def _rag_kwargs(**overrides):
    base = dict(user_id=42, question='سیاست بازگشت کالا چیست؟', document_id=None, top_k=5, model='mimo-v2.5')
    base.update(overrides)
    return base


# ── Moderation blocks before embedding, reserve, and upstream ──────────────

class TestRagModerationGate:
    @pytest.mark.asyncio
    async def test_blocked_question_never_reaches_upstream_or_opens_a_reservation(self):
        verdict = Verdict(decision='block', category='sexual', severity='high',
                           rule_id=9, message_fa=_BLOCK_MESSAGE)
        with _RagPatches(verdict=verdict) as p:
            result = await rag_mod.query_documents(**_rag_kwargs())

        assert result['answer'] == _BLOCK_MESSAGE
        assert result['sources'] == []
        p.embed_single.assert_not_called()
        p.fake_http.post.assert_not_called()
        p.billing_instance.reserve.assert_not_called()
        p.release_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_question_falls_back_to_block_message_fa_constant(self):
        from services.moderation import BLOCK_MESSAGE_FA
        verdict = Verdict(decision='block', category='other', severity='high', message_fa=None)
        with _RagPatches(verdict=verdict):
            result = await rag_mod.query_documents(**_rag_kwargs())
        assert result['answer'] == BLOCK_MESSAGE_FA

    @pytest.mark.asyncio
    async def test_screen_request_called_with_question_as_a_user_message(self):
        q = 'این یک سوال آزمایشی است'
        with _RagPatches() as p:
            await rag_mod.query_documents(**_rag_kwargs(question=q))
        p.screen_request.assert_awaited_once()
        call_args = p.screen_request.await_args
        assert call_args.args[0] == 42
        assert call_args.args[1] == [{'role': 'user', 'content': q}]


# ── chat_enabled kill switch blocks before moderation is even checked ─────

class TestRagChatDisabledGate:
    @pytest.mark.asyncio
    async def test_disabled_never_reaches_moderation_upstream_or_reserve(self):
        with _RagPatches(chat_enabled=False) as p:
            result = await rag_mod.query_documents(**_rag_kwargs())
        assert result['answer'] == rag_mod._CHAT_DISABLED_MESSAGE
        p.screen_request.assert_not_called()
        p.fake_http.post.assert_not_called()
        p.billing_instance.reserve.assert_not_called()


# ── Free-tier / quota gates block before embedding and reserve ────────────

class TestRagFreeTierAndQuotaGates:
    @pytest.mark.asyncio
    async def test_free_tier_gate_blocks_before_embedding_and_reserve(self):
        gate = {'code': 'free_lifetime_exhausted', 'message': 'سقف رایگان تمام شد', 'retry_after_seconds': 0}
        with _RagPatches(ft_gate=gate) as p:
            result = await rag_mod.query_documents(**_rag_kwargs())
        assert result['answer'] == 'سقف رایگان تمام شد'
        p.embed_single.assert_not_called()
        p.billing_instance.reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_quota_gate_blocks_before_embedding_and_reserve(self):
        gate = {'limit': 100, 'used': 100, 'source': 'package', 'retry_after_seconds': 300}
        with _RagPatches(q_gate=gate) as p:
            result = await rag_mod.query_documents(**_rag_kwargs())
        assert 'سقف' in result['answer']
        p.embed_single.assert_not_called()
        p.billing_instance.reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_free_tier_gate_runs_before_quota_gate(self):
        gate = {'code': 'free_hourly_throttle', 'message': 'ساعتی', 'retry_after_seconds': 5}
        with _RagPatches(ft_gate=gate) as p:
            await rag_mod.query_documents(**_rag_kwargs())
        p.user_quota_check.assert_not_called()


# ── A clean question passes through unchanged and is billed ────────────────

class TestRagCleanQueryBilledUnchanged:
    @pytest.mark.asyncio
    async def test_clean_question_bills_via_reserve_call_settle_release(self):
        with _RagPatches() as p:
            result = await rag_mod.query_documents(**_rag_kwargs())

        assert result['answer'] == 'پاسخ نمونه بر اساس سند'
        p.billing_instance.reserve.assert_awaited_once()
        p.fake_http.post.assert_awaited_once()
        p.bill_mock.assert_awaited_once()
        p.release_spy.assert_awaited_once()
        # The reservation object passed to release must be the one reserve()
        # returned, not a fresh/empty one.
        released_reservation = p.release_spy.await_args.args[0]
        assert released_reservation['reservation_id'] == 'rag-resv-1'
        assert result['billing']['cost'] == 77
        assert result['billing']['currency'] == 'IRT'

    @pytest.mark.asyncio
    async def test_question_reaches_upstream_byte_for_byte_unchanged(self):
        q = 'ساعات کاری پشتیبانی چیست؟'
        with _RagPatches() as p:
            await rag_mod.query_documents(**_rag_kwargs(question=q))
        _, kwargs = p.fake_http.post.await_args
        sent_messages = kwargs['json']['messages']
        assert sent_messages[-1] == {'role': 'user', 'content': q}

    @pytest.mark.asyncio
    async def test_bill_stream_usage_called_with_the_model_that_actually_answered(self):
        with _RagPatches(resolved_model='bynara/mimo-v2.5') as p:
            await rag_mod.query_documents(**_rag_kwargs())
        args, kwargs = p.bill_mock.await_args
        assert args[0] == 42
        assert args[1]['model'] == 'bynara/mimo-v2.5'


# ── No relevant content: never reserves, never calls upstream ─────────────

class TestRagNoRelevantContentBillsNothing:
    @pytest.mark.asyncio
    async def test_no_chunks_found_never_reserves_or_calls_upstream(self, caplog):
        """Drives the GENUINE "zero chunks retrieved anywhere" path: both
        the keyword search (mocked to []) and the real pgvector fallback
        branch's `session.execute().fetchall()` (see
        _rag_fake_async_session -- a real, properly-awaitable AsyncMock)
        come back empty, so query_documents reaches its own "no rows"
        return, not the `except Exception` around session.execute()."""
        with caplog.at_level(logging.ERROR, logger='services.rag'):
            with _RagPatches(rows=[]) as p:
                result = await rag_mod.query_documents(**_rag_kwargs())

        # Pins the fix: if session.execute() ever again hits a non-awaitable
        # mock, query_documents logs exactly this message and returns a
        # DIFFERENT string ('خطا در جستجوی اسناد.') that does not contain
        # 'پیدا نشد' -- so this assertion catches a regression back into
        # the exception path even if the answer text coincidentally still
        # looked plausible.
        assert 'Vector search failed' not in caplog.text
        assert 'پیدا نشد' in result['answer']
        p.fake_http.post.assert_not_called()
        p.billing_instance.reserve.assert_not_called()


# ── Insufficient balance: refused, upstream never called ──────────────────

class TestRagInsufficientBalance:
    @pytest.mark.asyncio
    async def test_insufficient_balance_refused_before_upstream(self):
        from services.billing import InsufficientBalanceError

        async def _reserve_boom(*a, **k):
            raise InsufficientBalanceError('no balance')

        with _RagPatches() as p:
            p.billing_instance.reserve = _reserve_boom
            result = await rag_mod.query_documents(**_rag_kwargs())

        assert result['answer'] == rag_mod._INSUFFICIENT_BALANCE_MESSAGE
        p.fake_http.post.assert_not_called()


# ── Fail-safe: a moderation layer that raises must NOT block a real user ──

class TestRagModerationFailSafe:
    @pytest.mark.asyncio
    async def test_detector_failure_allows_the_request(self):
        """Real screen_request exercised end to end (not the AsyncMock
        stand-in): an internal failure (_load_config raising) must ALLOW
        the request, never raise, and never block -- services/moderation.py's
        documented fail-safe contract, exercised for the RAG path too."""
        with _RagPatches() as p:
            with patch.object(rag_mod, 'screen_request', moderation_mod.screen_request), \
                 patch.object(moderation_mod, '_load_config', AsyncMock(side_effect=RuntimeError('detector down'))):
                result = await rag_mod.query_documents(**_rag_kwargs())

        assert result['answer'] == 'پاسخ نمونه بر اساس سند'
        p.fake_http.post.assert_awaited_once()
        p.billing_instance.reserve.assert_awaited_once()


# ── Gate ordering: chat_enabled -> moderation -> free-tier -> quota -> reserve

class TestRagGateOrdering:
    @pytest.mark.asyncio
    async def test_gate_order_matches_chat_preflight_plus_reserve(self):
        order: list[str] = []

        async def _flag(key):
            order.append('chat_enabled')
            assert key == 'chat_enabled'
            return True

        async def _screen(uid, messages, conversation_id=None):
            order.append('moderation')
            return Verdict(decision='allow')

        async def _ft(uid, models):
            order.append('free_tier')
            return None

        async def _q(uid):
            order.append('quota')
            return None

        with _RagPatches() as p:
            original_reserve = p.billing_instance.reserve

            async def _reserve(*a, **k):
                order.append('reserve')
                return await original_reserve(*a, **k)
            p.billing_instance.reserve = _reserve

            with patch.object(rag_mod, 'get_site_flag', _flag), \
                 patch.object(rag_mod, 'screen_request', _screen), \
                 patch.object(rag_mod, '_free_tier_check', _ft), \
                 patch.object(rag_mod, '_user_quota_check', _q):
                await rag_mod.query_documents(**_rag_kwargs())

        assert order == ['chat_enabled', 'moderation', 'free_tier', 'quota', 'reserve']
