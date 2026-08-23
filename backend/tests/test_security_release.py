"""Regression checks for SanjabAI security and release contracts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_auth_uses_constant_time_header_token_and_no_query_token():
    # app.py is a thin orchestrator (router-per-domain architecture, see
    # CLAUDE.md) — the actual admin_required() check lives in
    # dependencies.py, not here. Every backend module gets scanned so this
    # still catches a query-param admin token from any file, not just this
    # one.
    source = (ROOT / "dependencies.py").read_text()
    assert "hmac.compare_digest" in source
    for path in ROOT.glob("*.py"):
        assert "request.query_params.get('admin_token')" not in path.read_text()


def test_admin_token_is_required_by_compose_without_public_fallback():
    # docker-compose.yml is the file the stack actually runs on and the one
    # CI deploys with. This used to read docker-compose.sanjabai.yml, a stale
    # copy predating the Caddy services — guarding a file nobody deploys.
    source = (ROOT.parent / "docker-compose.yml").read_text()
    assert "ADMIN_TOKEN:?ADMIN_TOKEN must be set in .env" in source
    assert "sanjabai-admin-secret-change-me" not in source


def test_rate_limiter_fails_closed_when_redis_is_unavailable():
    source = (ROOT / "security.py").read_text()
    assert "return False, 0" in source


def test_sanjabai_frontend_is_published_on_3003():
    source = (ROOT.parent / "docker-compose.yml").read_text()
    assert '"0.0.0.0:3003:3000"' in source


def test_ci_deploys_the_live_compose_file():
    """CI must deploy the stack that actually runs.

    The deploy job ran `docker compose -f docker-compose.sanjabai.yml up -d`:
    the stale compose file (no Caddy), and a bare `up -d` that recreates
    depends_on services and can rebuild an image from the working tree
    mid-deploy. Both are the documented way to break this box.
    """
    ci = (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text()
    deploy = ci.split("name: Deploy via SSH", 1)[1]
    assert "-f docker-compose.yml" in deploy
    assert "docker compose -f docker-compose.sanjabai.yml" not in deploy
    assert "--no-deps --no-build --force-recreate" in deploy
