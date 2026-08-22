"""Regression tests for honest email-send reporting.

Two related bugs fixed together:

1. `POST /auth/send-welcome` (backend/auth.py) used to return
   `{'status': 'queued'}` whenever `send_email()` returned False. 'queued'
   implies a background queue exists and will retry delivery later --
   there is no such queue. `send_email` (backend/dependencies.py) either
   sends synchronously or does nothing at all, and outbound SMTP is
   permanently blocked at the host level on this production server (every
   SMTP port measured BLOCKED), so the False branch is not a transient
   "try again later" -- nothing was sent and, on this host, nothing ever
   will be via SMTP. The endpoint must let a caller distinguish "sent"
   from "not sent" without guessing, using a Persian user-facing message
   that does not claim delivery is still coming.

2. `send_email`'s default `SMTP_FROM` was `noreply@sanjabai.ir` -- the
   dead domain retired in commit 1ab7e4b when the project moved to
   sanjabai.com (that commit touched 8 files and missed this default).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_row


class TestSendWelcomeEmailHonesty:
    def _call(self, client, mock_async_session, *, send_email_ok):
        user = make_row(id=7, email='user@example.com')

        async def mock_execute(stmt, *a, **k):
            result = MagicMock()
            result.fetchone.return_value = user
            return result

        mock_async_session.execute = mock_execute

        with patch('auth._get_user_id', new=AsyncMock(return_value=7)), \
             patch('auth.send_email', new=AsyncMock(return_value=send_email_ok)) as mock_send:
            resp = client.post('/auth/send-welcome')
        return resp, mock_send

    def test_successful_send_reports_status_sent(self, client, mock_async_session):
        resp, _ = self._call(client, mock_async_session, send_email_ok=True)
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'sent'
        # Persian user-facing message required.
        assert any('؀' <= ch <= 'ۿ' for ch in body.get('message', ''))

    def test_failed_send_does_not_claim_queued(self, client, mock_async_session):
        """The old code returned {'status': 'queued'} here -- implying a
        retry mechanism that does not exist. This must never come back."""
        resp, _ = self._call(client, mock_async_session, send_email_ok=False)
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] != 'queued'
        assert body['status'] == 'not_sent'

    def test_failed_send_status_is_distinguishable_from_success(self, client, mock_async_session):
        """A caller must be able to tell sent from not-sent from `status`
        alone, with no other field required."""
        sent_resp, _ = self._call(client, mock_async_session, send_email_ok=True)
        not_sent_resp, _ = self._call(client, mock_async_session, send_email_ok=False)
        assert sent_resp.json()['status'] != not_sent_resp.json()['status']

    def test_failed_send_message_is_persian_and_does_not_promise_delivery(self, client, mock_async_session):
        resp, _ = self._call(client, mock_async_session, send_email_ok=False)
        message = resp.json().get('message', '')
        assert any('؀' <= ch <= 'ۿ' for ch in message), 'user-facing message must be Persian'
        # Must not resurrect the "it's coming" lie in different words.
        for banned in ('queued', 'صف', 'به‌زودی', 'بزودی'):
            assert banned not in message


class TestSendEmailLogging:
    """send_email's no-op branch must be loud and go through `logging`,
    like neighbouring modules -- not a bare print() that vanishes in
    production log handling."""

    def test_no_smtp_host_logs_a_warning_not_a_print(self, caplog):
        import dependencies
        import logging

        with patch.object(dependencies, 'SMTP_HOST', ''):
            with caplog.at_level(logging.WARNING, logger='dependencies'):
                result = _run(dependencies.send_email('a@b.com', 'subject', 'body'))

        assert result is False
        assert any(
            record.name == 'dependencies' and record.levelno == logging.WARNING
            for record in caplog.records
        ), 'expected a WARNING-level log record from the dependencies logger'
        # The message must explain *why* nothing was sent (host-level SMTP
        # block), not just that it wasn't.
        combined = ' '.join(r.getMessage() for r in caplog.records)
        assert 'a@b.com' in combined

    def test_send_email_default_from_is_not_the_dead_ir_domain(self):
        import dependencies
        assert dependencies.SMTP_FROM != 'noreply@sanjabai.ir'
        assert dependencies.SMTP_FROM == 'noreply@sanjabai.com'


def _run(coro):
    import asyncio
    return asyncio.run(coro)
