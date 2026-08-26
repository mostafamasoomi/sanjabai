"""Tests for the three site_settings.py flags this task wires to real
behaviour: ``signups_enabled`` (auth.py), ``chat_enabled`` (chat.py +
chat_web.py + chat_smart.py + chat_compare.py -- all four chat entry
points), and ``image_generation_enabled`` (images.py).

Mirrors tests/test_public_model_ids.py's `_bypass_pipeline` idiom: auth,
free-tier, billing, and provider routing are patched directly on the shared
`chat` module object, since chat_web.py/chat_smart.py/chat_compare.py all
resolve those names through `chat.<name>` at call time (see chat.py's
MONKEYPATCH CONTRACT docstring) -- patching `chat_mod.X` therefore affects
all four routes uniformly. images.py gets the equivalent treatment,
following tests/test_images.py's `_BasePatches`.

The fail-open tests do NOT mock ``get_site_flag`` -- they call the real
function and break only ``site_settings``'s OWN ``rds``/``async_session``
references (reassigning the name in site_settings's namespace, not mutating
the shared singleton objects other code in the same request still needs),
following tests/test_site_settings.py's DB-error idiom. That is what proves
the *wiring* is fail-open, not just that get_site_flag itself is (already
covered by test_site_settings.py).
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import auth as auth_mod
import chat as chat_mod
import chat_web as chat_web_mod
import images as images_mod
import site_settings
import database as _db


AUTH_HEADERS = {'Authorization': 'Bearer test-token'}
CAPTCHA = {'captcha_token': 'test-token', 'captcha_answer': '1234'}


# ── Shared fakes ────────────────────────────────────────────────────────

class _FakeProvider:
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _billing_mock():
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'resv-1'})
    instance.release = AsyncMock(return_value=None)
    instance.settle = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


def _upstream_ok(body=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'ok'}}]})
    resp.content = b'{}'
    return resp


def _break_site_settings_store():
    """Context managers that make get_site_flag's cache AND DB reads both
    fail, isolated to site_settings's own module namespace only -- the
    shared `rds`/`async_session` objects other code in the same request
    still needs stay intact (see module docstring)."""
    broken_rds = AsyncMock()
    broken_rds.get = AsyncMock(side_effect=RuntimeError('settings cache down'))
    return (
        patch.object(site_settings, 'async_session', None),
        patch.object(site_settings, 'rds', broken_rds),
    )


# ── signups_enabled -> auth.py ─────────────────────────────────────────

class TestSignupsEnabledFlag:
    def test_on_proceeds_past_gate(self, client, mock_async_session):
        from tests.conftest import make_result
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(auth_mod, 'get_site_flag', AsyncMock(return_value=True)), \
             patch('app.rds.setex', new_callable=AsyncMock), \
             patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            resp = client.post('/auth/signup', json={
                'email': 'flagon@example.com', 'password': 'securepass123', **CAPTCHA,
            })
        assert resp.status_code != 403

    def test_off_returns_403_persian_and_skips_captcha(self, client):
        captcha_delete = AsyncMock()
        with patch.object(auth_mod, 'get_site_flag', AsyncMock(return_value=False)), \
             patch('app.rds.delete', captcha_delete), \
             patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            # Deliberately send NO captcha fields: if the flag gate were not
            # first, this would 400 on "captcha missing", not 403.
            resp = client.post('/auth/signup', json={
                'email': 'flagoff@example.com', 'password': 'securepass123',
            })
        assert resp.status_code == 403
        # Still an equality assertion, deliberately: the body must be exactly
        # these two keys and nothing else. The Persian under `detail` is
        # byte-identical to what it always was -- that is the whole point of
        # the bilingual contract (backend/i18n.py), which adds a sibling and
        # never moves the original.
        assert resp.json() == {
            'detail': 'ثبت‌نام کاربران جدید موقتاً غیرفعال است. لطفاً بعداً دوباره تلاش کنید.',
            'detail_en': 'Sign-ups are temporarily disabled. Please try again later.',
        }
        captcha_delete.assert_not_awaited()

    def test_settings_store_broken_fails_open_signup_not_blocked(self, client, mock_async_session):
        from tests.conftest import make_result
        mock_async_session._execute_result = make_result(fetchone=None)
        p1, p2 = _break_site_settings_store()
        with p1, p2, \
             patch('app.rds.setex', new_callable=AsyncMock), \
             patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            resp = client.post('/auth/signup', json={
                'email': 'flagbroken@example.com', 'password': 'securepass123', **CAPTCHA,
            })
        assert resp.status_code != 403


# ── chat_enabled -> chat.py / chat_web.py / chat_smart.py / chat_compare.py ─

@pytest.fixture
def _chat_bypass(mock_async_session):
    """Everything downstream of the chat_enabled gate mocked out, for all
    four chat entry points at once (they all resolve these names through
    `chat.<name>` -- see chat.py's MONKEYPATCH CONTRACT docstring)."""
    billing_cls, billing_instance = _billing_mock()
    fake_http = MagicMock()
    fake_http.post = AsyncMock(return_value=_upstream_ok())
    patches = [
        patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)),
        patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m or 'tencent-hy3')),
        patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='tencent-hy3')),
        patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)),
        patch.object(chat_mod, 'BillingService', billing_cls),
        patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)),
        patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)),
        patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())),
        patch.object(chat_mod, '_track_usage', AsyncMock(return_value={})),
        patch.object(_db, '_real_http', fake_http),
    ]
    for p in patches:
        p.start()
    yield billing_instance
    for p in patches:
        p.stop()


@pytest.fixture
def _chat_off(mock_async_session):
    """Auth passes, chat_enabled is False, and a BillingService spy to prove
    no reservation is ever attempted while the gate refuses."""
    billing_cls, billing_instance = _billing_mock()
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_web_mod, 'get_site_flag', AsyncMock(return_value=False)), \
         patch.object(chat_mod, 'BillingService', billing_cls):
        yield billing_instance


_REFUSAL = {
    'error': {
        # Persian byte-identical to what it always was; `message_en` is the
        # sibling backend/i18n.py::err_openai adds. `type` and `code` are the
        # contract fields OpenAI-compatible clients branch on and must not
        # move -- asserting the whole body by equality is what keeps that true.
        'message': 'گفتگو موقتاً در دسترس نیست',
        'message_en': 'Chat is temporarily unavailable.',
        'type': 'service_unavailable',
        'code': 'chat_disabled',
    },
}


class TestChatEnabledFlagCompletions:
    def test_on_proceeds_past_gate(self, client, _chat_bypass):
        with patch.object(chat_web_mod, 'get_site_flag', AsyncMock(return_value=True)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text

    def test_off_refuses_and_takes_no_reservation(self, client, _chat_off):
        resp = client.post(
            '/v1/chat/completions',
            json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'سلام'}]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503
        assert resp.json() == _REFUSAL
        _chat_off.reserve.assert_not_awaited()

    def test_settings_store_broken_fails_open(self, client, _chat_bypass):
        p1, p2 = _break_site_settings_store()
        with p1, p2:
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text


class TestChatEnabledFlagWithFile:
    def test_on_proceeds_past_gate(self, client, _chat_bypass):
        with patch.object(chat_web_mod, 'get_site_flag', AsyncMock(return_value=True)):
            resp = client.post(
                '/v1/chat/with-file',
                data={'model': 'tencent-hy3', 'messages': '[]'},
                files={'file': ('note.txt', b'hello world', 'text/plain')},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text

    def test_off_refuses_and_takes_no_reservation(self, client, _chat_off):
        resp = client.post(
            '/v1/chat/with-file',
            data={'model': 'tencent-hy3', 'messages': '[]'},
            files={'file': ('note.txt', b'hello world', 'text/plain')},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503
        assert resp.json() == _REFUSAL
        _chat_off.reserve.assert_not_awaited()

    def test_settings_store_broken_fails_open(self, client, _chat_bypass):
        p1, p2 = _break_site_settings_store()
        with p1, p2:
            resp = client.post(
                '/v1/chat/with-file',
                data={'model': 'tencent-hy3', 'messages': '[]'},
                files={'file': ('note.txt', b'hello world', 'text/plain')},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text


class TestChatEnabledFlagSmartChat:
    def test_on_proceeds_past_gate(self, client, _chat_bypass):
        with patch.object(chat_web_mod, 'get_site_flag', AsyncMock(return_value=True)):
            resp = client.post(
                '/v1/smart-chat',
                json={'messages': [{'role': 'user', 'content': 'سلام'}], 'stream': False},
                headers={**AUTH_HEADERS, 'X-Smart-Model': 'tencent-hy3'},
            )
        assert resp.status_code == 200, resp.text

    def test_off_refuses_and_takes_no_reservation(self, client, _chat_off):
        resp = client.post(
            '/v1/smart-chat',
            json={'messages': [{'role': 'user', 'content': 'سلام'}], 'stream': False},
            headers={**AUTH_HEADERS, 'X-Smart-Model': 'tencent-hy3'},
        )
        assert resp.status_code == 503
        assert resp.json() == _REFUSAL
        _chat_off.reserve.assert_not_awaited()

    def test_settings_store_broken_fails_open(self, client, _chat_bypass):
        p1, p2 = _break_site_settings_store()
        with p1, p2:
            resp = client.post(
                '/v1/smart-chat',
                json={'messages': [{'role': 'user', 'content': 'سلام'}], 'stream': False},
                headers={**AUTH_HEADERS, 'X-Smart-Model': 'tencent-hy3'},
            )
        assert resp.status_code == 200, resp.text


class TestChatEnabledFlagCompare:
    def test_on_proceeds_past_gate(self, client, _chat_bypass):
        with patch.object(chat_web_mod, 'get_site_flag', AsyncMock(return_value=True)):
            resp = client.post(
                '/v1/compare',
                json={
                    'model_a': 'tencent-hy3', 'model_b': 'mistral-large',
                    'messages': [{'role': 'user', 'content': 'سلام'}],
                },
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text

    def test_off_refuses_and_takes_no_reservation(self, client, _chat_off):
        resp = client.post(
            '/v1/compare',
            json={
                'model_a': 'tencent-hy3', 'model_b': 'mistral-large',
                'messages': [{'role': 'user', 'content': 'سلام'}],
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503
        assert resp.json() == _REFUSAL
        _chat_off.reserve.assert_not_awaited()

    def test_settings_store_broken_fails_open(self, client, _chat_bypass):
        p1, p2 = _break_site_settings_store()
        with p1, p2:
            resp = client.post(
                '/v1/compare',
                json={
                    'model_a': 'tencent-hy3', 'model_b': 'mistral-large',
                    'messages': [{'role': 'user', 'content': 'سلام'}],
                },
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text


# ── image_generation_enabled -> images.py ──────────────────────────────

def _image_row():
    return types.SimpleNamespace(
        provider_model_id='pollinations/flux', availability='available',
        image_price_per_unit=1000, markup_pct=None,
    )


@pytest.fixture
def _image_bypass(mock_async_session):
    billing_cls, billing_instance = _billing_mock()
    fake_http = MagicMock()
    fake_http.post = AsyncMock(return_value=_upstream_ok(
        {'created': 1, 'data': [{'url': 'https://example.com/x.png'}]}
    ))
    patches = [
        patch.object(images_mod, '_get_user_id', AsyncMock(return_value=42)),
        patch.object(images_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)),
        patch.object(images_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())),
        patch.object(images_mod, '_load_image_model', AsyncMock(return_value=_image_row())),
        patch.object(images_mod, 'get_effective_markup_pct', AsyncMock(return_value=0)),
        patch.object(images_mod, 'BillingService', billing_cls),
        patch.object(images_mod, '_http', fake_http),
    ]
    for p in patches:
        p.start()
    yield billing_instance
    for p in patches:
        p.stop()


@pytest.fixture
def _image_off(mock_async_session):
    billing_cls, billing_instance = _billing_mock()
    with patch.object(images_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(images_mod, 'get_site_flag', AsyncMock(return_value=False)), \
         patch.object(images_mod, 'BillingService', billing_cls):
        yield billing_instance


# The OpenAI-compatible refusal shape. `message` is byte-identical to what it
# always was and `message_en` is the sibling the client picks when the UI is in
# English (backend/i18n.py, frontend lib/i18n.ts::detailFor). `type` and `code`
# are contract fields that OpenAI-compatible clients branch on and must never
# move -- asserting the whole body by equality is what keeps that true.
_IMAGE_REFUSAL = {
    'error': {
        'message': 'تولید تصویر موقتاً در دسترس نیست',
        'message_en': 'Image generation is temporarily unavailable.',
        'type': 'service_unavailable',
        'code': 'image_generation_disabled',
    },
}


class TestImageGenerationEnabledFlag:
    def test_on_proceeds_past_gate(self, client, _image_bypass):
        with patch.object(images_mod, 'get_site_flag', AsyncMock(return_value=True)):
            resp = client.post(
                '/v1/images/generations',
                json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text

    def test_off_refuses_and_takes_no_reservation(self, client, _image_off):
        resp = client.post(
            '/v1/images/generations',
            json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503
        assert resp.json() == _IMAGE_REFUSAL
        _image_off.reserve.assert_not_awaited()

    def test_settings_store_broken_fails_open(self, client, _image_bypass):
        p1, p2 = _break_site_settings_store()
        with p1, p2:
            resp = client.post(
                '/v1/images/generations',
                json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
