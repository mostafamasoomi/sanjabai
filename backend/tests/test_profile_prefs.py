"""Tests for the smart_router_enabled / compression_enabled profile
preferences (server-side boolean validation and round-trip through
GET/PUT /auth/profile).

compression_enabled defaults to False -- turning compression on changes a
user's input token count, i.e. their bill, so nobody gets that by accident.
smart_router_enabled defaults to True.
"""
from fastapi.testclient import TestClient

from app import app
from tests.conftest import make_result, make_row

client = TestClient(app)


def _spy_on_execute(session):
    """Wrap ``session.execute`` to record every call's positional args
    (statement + params), without changing what it returns. Used to prove
    the PUT handler actually persists the merged preferences dict, not just
    that it returns 200 -- same pattern as
    tests/test_admin_model_control.py's ``_spy_on_execute``.
    """
    calls: list[tuple] = []
    orig_execute = session.execute

    async def spy_execute(*args, **kwargs):
        calls.append(args)
        return await orig_execute(*args, **kwargs)

    session.execute = spy_execute
    return calls


class TestProfilePrefsGetDefaults:
    def test_get_profile_defaults_when_no_preferences_stored(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(
            id=1, email='a@b.com', display_name='A', avatar_url=None, bio=None,
            timezone='Asia/Tehran', language='fa',
            preferences={},
            created_at=None, referral_code=None,
        ))
        resp = client.get('/auth/profile', headers=auth_headers)
        assert resp.status_code == 200
        prefs = resp.json()['preferences']
        assert prefs['smart_router_enabled'] is True
        assert prefs['compression_enabled'] is False

    def test_get_profile_echoes_stored_values_not_defaults(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(
            id=1, email='a@b.com', display_name='A', avatar_url=None, bio=None,
            timezone='Asia/Tehran', language='fa',
            preferences={'smart_router_enabled': False, 'compression_enabled': True},
            created_at=None, referral_code=None,
        ))
        resp = client.get('/auth/profile', headers=auth_headers)
        assert resp.status_code == 200
        prefs = resp.json()['preferences']
        assert prefs['smart_router_enabled'] is False
        assert prefs['compression_enabled'] is True


class TestProfilePrefsPutValidation:
    def test_put_accepts_true_false(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'smart_router_enabled': True, 'compression_enabled': False},
        })
        assert resp.status_code == 200
        assert 'preferences' in resp.json()['updated']

    def test_put_rejects_integer_one_for_smart_router(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'smart_router_enabled': 1},
        })
        assert resp.status_code == 400
        assert 'روتر هوشمند' in resp.json()['detail']

    def test_put_rejects_integer_one_for_compression(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'compression_enabled': 1},
        })
        assert resp.status_code == 400
        assert 'فشرده‌سازی' in resp.json()['detail']

    def test_put_rejects_string_true(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'smart_router_enabled': 'true'},
        })
        assert resp.status_code == 400

    def test_put_rejects_null(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'compression_enabled': None},
        })
        assert resp.status_code == 400

    def test_400_body_carries_persian_text(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={}))
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'smart_router_enabled': 'yes'},
        })
        assert resp.status_code == 400
        text = resp.json()['detail']
        assert any('؀' <= ch <= 'ۿ' for ch in text)


class TestProfilePrefsPutPersistence:
    def test_setting_one_key_does_not_wipe_the_other_or_unrelated_prefs(self, mock_async_session, auth_headers):
        mock_async_session._execute_result = make_result(fetchone=make_row(preferences={
            'compression_enabled': True,
            'theme': 'light',
            'default_model': 'gpt-x',
        }))
        calls = _spy_on_execute(mock_async_session)
        resp = client.put('/auth/profile', headers=auth_headers, json={
            'preferences': {'smart_router_enabled': False},
        })
        assert resp.status_code == 200

        # Find the UPDATE call -- it is the second execute (first is the
        # SELECT that loads existing_prefs) and carries the params dict as
        # its second positional argument.
        update_calls = [c for c in calls if len(c) >= 2 and isinstance(c[1], dict)]
        assert len(update_calls) == 1
        persisted_prefs = update_calls[0][1]['preferences']
        assert persisted_prefs['smart_router_enabled'] is False
        # unrelated / other new key untouched by this PUT
        assert persisted_prefs['compression_enabled'] is True
        assert persisted_prefs['theme'] == 'light'
        assert persisted_prefs['default_model'] == 'gpt-x'
