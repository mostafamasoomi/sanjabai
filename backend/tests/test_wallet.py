"""
Tests for wallet, ledger, topup, and conversations
"""
import types
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
        # topup() now routes the actual wallet.balance mutation through
        # services.billing.credit_wallet (SqlBillingRepo), which issues a
        # richer query sequence than the old raw-SQL implementation did: a
        # payment_orders lookup, this route's own duplicate-by-reason check,
        # credit_wallet's ledger_has_key idempotency check, a FOR UPDATE
        # wallet lock, a wallet select, a wallet balance update, and a final
        # wallet re-read for the response. A fixed pop-list can't express
        # that reliably, so use a small table-name-aware fake session
        # instead (same pattern as tests/test_wallet_balance_charge.py's
        # _FakeSession).
        class _FakeTopupSession:
            def __init__(self):
                self.wallet = types.SimpleNamespace(user_id=1, balance=10000, reserved=0)
                self.added = []

            @staticmethod
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

            async def execute(self, stmt, params=None, *a, **k):
                result = MagicMock()
                result.fetchone.return_value = None
                text_sql = str(stmt)
                if "payment_orders" in text_sql:
                    result.fetchone.return_value = types.SimpleNamespace(
                        id='po1', status='completed', amount=50000
                    )
                    return result
                if "FROM ledger WHERE reason" in text_sql:
                    return result  # no duplicate topup by reason
                tname = self._table_name(stmt)
                if tname == "ledger":
                    return result  # credit_wallet's ledger_has_key(): no existing key
                if tname == "wallet":
                    if type(stmt).__name__ == "Update":
                        p = stmt.compile().params
                        if "balance" in p:
                            self.wallet.balance = p["balance"]
                    else:
                        result.fetchone.return_value = (self.wallet,)
                    return result
                return result

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                return None

        fake = _FakeTopupSession()
        mock_async_session.execute = fake.execute
        mock_async_session.add = fake.add
        mock_async_session.commit = fake.commit

        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.post('/wallet/topup', json={'amount': 50000, 'payment_order_id': 'po1'},
                                   headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['balance_after'] == 60000

        # The core regression this test protects: wallet.balance itself is
        # actually updated, not just a Ledger row appended.
        assert fake.wallet.balance == 60000
        ledger_rows = [o for o in fake.added if type(o).__name__ == "Ledger"]
        assert len(ledger_rows) == 1
        assert ledger_rows[0].amount == 50000
        assert ledger_rows[0].idempotency_key == 'topup:po1'

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