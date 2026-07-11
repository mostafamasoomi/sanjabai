"""Regression checks for MultiAI security and release contracts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_auth_uses_constant_time_header_token_and_no_query_token():
    source = (ROOT / "app.py").read_text()
    assert "hmac.compare_digest" in source
    assert "request.query_params.get('admin_token')" not in source


def test_admin_token_is_required_by_compose_without_public_fallback():
    source = (ROOT.parent / "docker-compose.multiai.yml").read_text()
    assert "ADMIN_TOKEN:?ADMIN_TOKEN must be set in .env" in source
    assert "multiai-admin-secret-change-me" not in source


def test_rate_limiter_fails_closed_when_redis_is_unavailable():
    source = (ROOT / "security.py").read_text()
    assert "return False, 0" in source


def test_multiai_frontend_is_published_on_3003():
    source = (ROOT.parent / "docker-compose.multiai.yml").read_text()
    assert '"0.0.0.0:3003:3000"' in source
