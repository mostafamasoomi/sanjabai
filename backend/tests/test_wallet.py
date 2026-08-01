"""
Tests for wallet, ledger, topup, and conversations
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import make_result, make_row


class TestWallet:
    def test_wallet_authenticated(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(balance=50000)
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/wallet', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['balance'] == 50000

    def test_wallet_unauthenticated(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
            response = client.get('/wallet')
            assert response.status_code == 401

    def test_wallet_zero_balance(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(balance=0)
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/wallet', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['balance'] == 0


class TestLedger:
    def test_ledger_with_transactions(self, client, mock_async_session):
        # Same COUNT-then-page shape as /conversations — see the comment on
        # test_list_conversations.
        mock_async_session._execute_result = make_result(
            fetchone=make_row(c=1),
            fetchall=[
                make_row(id=1, amount=10000, balance_after=60000, reason='شارژ', created_at='2024-01-01')
            ],
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/wallet/ledger', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert len(response.json()['items']) == 1

    def test_ledger_empty(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(c=0), fetchall=[])
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/wallet/ledger', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['items'] == []

    def test_ledger_unauthenticated(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
            response = client.get('/wallet/ledger')
            assert response.status_code == 401


class TestTopup:
    def test_topup_success(self, client, mock_async_session):
        # topup() makes three sequential session.execute() calls against a
        # *completed* payment order (looked up by payment_order_id) — the
        # order row, a duplicate-ledger-entry check, then the current
        # balance — each needing a different shaped result, so the fixture's
        # single shared _execute_result isn't enough; override execute with
        # a call-order-aware stand-in instead.
        results = [
            make_result(fetchone=make_row(id='po1', status='completed', amount=50000)),
            make_result(fetchone=None),  # no duplicate ledger entry
            make_result(fetchone=make_row(balance=10000)),
        ]

        async def sequenced_execute(*args, **kwargs):
            return results[sequenced_execute.calls.pop(0)]
        sequenced_execute.calls = [0, 1, 2]
        mock_async_session.execute = sequenced_execute

        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.post('/wallet/topup', json={'amount': 50000, 'payment_order_id': 'po1'},
                                   headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['balance_after'] == 60000

    def test_topup_negative_amount(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.post('/wallet/topup', json={'amount': -100, 'payment_order_id': 'po1'},
                                   headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 400

    def test_topup_zero_amount(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.post('/wallet/topup', json={'amount': 0, 'payment_order_id': 'po1'},
                                   headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 400

    def test_topup_unauthenticated(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
            response = client.post('/wallet/topup', json={'amount': 10000, 'payment_order_id': 'po1'})
            assert response.status_code == 401


class TestConversations:
    def test_list_conversations(self, client, mock_async_session):
        # The endpoint issues two queries against the same session — a COUNT
        # (fetchone().c) then the page of rows (fetchall()) — and returns a
        # paginated envelope ({'items', 'total', 'page', 'limit'}), not a
        # bare list. mock_execute always returns this one _execute_result
        # for both calls, so it needs both fetchone and fetchall populated.
        mock_async_session._execute_result = make_result(
            fetchone=make_row(c=1),
            fetchall=[
                make_row(id=1, title='Test', model='gpt-4o', created_at='2024-01-01', updated_at='2024-01-01')
            ],
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/conversations', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert len(response.json()['items']) == 1

    def test_create_conversation(self, client, mock_async_session):
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.post('/conversations', json={
                'title': 'New Chat', 'model': 'claude-3', 'messages': [{'role': 'user', 'content': 'hi'}],
            }, headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200

    def test_delete_conversation(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(id=1, user_id=1)
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.delete('/conversations/1', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200

    def test_delete_not_found(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.delete('/conversations/999', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 404

    def test_get_not_owned(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/conversations/999', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 404

    def test_unauthenticated(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
            response = client.get('/conversations')
            assert response.status_code == 401