"""Tests for the pinned_context profile preference (server-side validation
and round-trip through GET/PUT /auth/profile)."""
from fastapi.testclient import TestClient

from app import app
from tests.conftest import make_result, make_row

client = TestClient(app)


class TestPinnedContextProfile:
    def test_get_profile_echoes_pinned_context(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(
            id=1, email='a@b.com', display_name='A', avatar_url=None, bio=None,
            timezone='Asia/Tehran', language='fa',
            preferences={'pinned_context': 'یادداشت من'},
            created_at=None, referral_code=None,
        ))
        resp = client.get('/auth/profile', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()['preferences']['pinned_context'] == 'یادداشت من'

    def test_put_profile_rejects_oversized_pinned_context(self, mock_async_session, auth_headers):
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'pinned_context': 'x' * 20001},
        })
        assert resp.status_code == 400

    def test_put_profile_rejects_non_string_pinned_context(self, mock_async_session, auth_headers):
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'pinned_context': 12345},
        })
        assert resp.status_code == 400

    def test_put_profile_accepts_valid_pinned_context(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'pinned_context': '# یادداشت\nمتن نمونه'},
        })
        assert resp.status_code == 200
        assert 'preferences' in resp.json()['updated']
