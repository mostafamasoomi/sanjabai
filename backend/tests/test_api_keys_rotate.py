"""Tests for API key rotation (`POST /api-keys/{id}/rotate`) and for the
truthfulness of what `GET /api-keys` (list) returns.

Context: the frontend used to fabricate a fake "full key" by appending the
database row id to the key prefix and let users copy/reveal that fabrication.
The fix is (a) the list endpoint must never return anything that could be
mistaken for a full key, and (b) a new rotate endpoint reuses the exact same
generation/hashing path as creation (`secrets.token_urlsafe` + `_hash_api_key`
from `api_keys.py`) to issue a fresh secret, returned raw exactly once, for a
key the caller owns.
"""
from fastapi.testclient import TestClient

from app import app
from tests.conftest import make_result, make_row

client = TestClient(app)


class TestRotateApiKey:
    def test_rotate_returns_new_key_different_from_created_key(self, mock_async_session, auth_headers):
        # Create the original key first.
        create_resp = client.post('/api-keys', headers=auth_headers, json={'name': 'Default'})
        assert create_resp.status_code == 200
        original_key = create_resp.json()['key']
        assert original_key.startswith('sk-')

        # Rotate it — the ownership/active lookup must find the row.
        mock_async_session._execute_result = make_result(fetchone=make_row(
            id=1, user_id=1, name='Default', key_prefix='sk-oldprefix1', scopes='read',
            active=True, revoked_at=None, expires_at=None, last_used=None, created_at=None,
        ))
        rotate_resp = client.post('/api-keys/1/rotate', headers=auth_headers)
        assert rotate_resp.status_code == 200
        rotated = rotate_resp.json()
        assert rotated['key'].startswith('sk-')
        assert rotated['key'] != original_key
        assert rotated['id'] == 1
        assert rotated['name'] == 'Default'

    def test_rotate_missing_key_is_404(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = client.post('/api-keys/999/rotate', headers=auth_headers)
        assert resp.status_code == 404

    def test_rotate_cannot_target_another_users_key(self, mock_async_session, auth_headers):
        # The row lookup is filtered by (id, user_id) at the SQL level, so a
        # key owned by a different user simply doesn't come back — same
        # observable outcome (404) as a missing key, which is deliberate:
        # it doesn't confirm to the caller that the id exists at all.
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = client.post('/api-keys/42/rotate', headers=auth_headers)
        assert resp.status_code == 404

    def test_rotate_refuses_an_inactive_key(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(
            id=2, user_id=1, name='Old', key_prefix='sk-revokedxxx', scopes='read',
            active=False, revoked_at='2026-01-01T00:00:00', expires_at=None,
            last_used=None, created_at=None,
        ))
        resp = client.post('/api-keys/2/rotate', headers=auth_headers)
        assert resp.status_code == 400

    def test_rotate_requires_auth(self, mock_async_session):
        resp = client.post('/api-keys/1/rotate')
        assert resp.status_code == 401

    def test_old_secret_no_longer_authenticates_after_rotation(self, mock_async_session):
        # Simulate the post-rotation DB state: the row's key_hash column no
        # longer matches a hash of the pre-rotation raw key, so the
        # ApiKey-lookup query in dependencies._get_user_id (filtered by
        # key_hash) finds nothing — exactly what happens for real once the
        # UPDATE in rotate_api_key has committed a new key_hash.
        mock_async_session._execute_result = make_result(fetchone=None)
        old_raw_key = 'sk-this-secret-was-rotated-away-1234567890'
        resp = client.get('/api-keys', headers={'Authorization': f'Bearer {old_raw_key}'})
        assert resp.status_code == 401


class TestListApiKeysNoFabrication:
    def test_list_response_has_no_key_field(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id=1, name='Default', key_prefix='sk-abcdefghijk', scopes='read',
                active=True, revoked_at=None, expires_at=None, last_used=None,
                created_at=None,
            ),
        ])
        resp = client.get('/api-keys', headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        item = body[0]
        assert 'key' not in item

    def test_list_masked_and_prefix_never_equal_a_full_key_length(self, mock_async_session, auth_headers):
        # A real raw key is `sk-` + 43 url-safe base64 chars (~46 chars total).
        # Neither `prefix` (always the fixed 12-char slice taken at creation)
        # nor `masked` (prefix + a fixed run of bullet characters) should ever
        # reach that length by incorporating anything else (like the row id).
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id=999, name='Default', key_prefix='sk-abcdefghij', scopes='read',
                active=True, revoked_at=None, expires_at=None, last_used=None,
                created_at=None,
            ),
        ])
        resp = client.get('/api-keys', headers=auth_headers)
        item = resp.json()[0]
        assert item['prefix'] == 'sk-abcdefghij'
        assert len(item['prefix']) == len('sk-abcdefghij')
        assert '999' not in item['masked']
        assert '999' not in item['prefix']
