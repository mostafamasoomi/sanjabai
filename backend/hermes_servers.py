"""Hermes server product -- server fleet management and the agent daemon
endpoints: `/hermes/servers/*` (owner-facing, session-cookie auth) and
`/hermes/agent/*` (the agent daemon running on the delivered VPS, token
auth via `Authorization: Bearer hsa-...`, not the session cookie).

Split out of hermes.py purely to stay under the house 500-line cap -- see
hermes.py's module docstring for the full product overview and the
IMPORT/MONKEYPATCH CONTRACT this file follows. Nothing here changed in the
move.

`import hermes` is done plainly at module scope, which is safe against the
hermes.py <-> hermes_servers.py circular import: nothing here touches a
`hermes` attribute until a function/decorator actually runs (the
`@hermes.router...` decorators below execute when *this* module is
imported, which hermes.py only does after `router = APIRouter()` has
already run -- see the bottom of hermes.py).
"""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

import hermes
from database import async_session
from i18n import err
from models import HermesServer, HermesServerSkill, HermesSkillCatalog, HermesAgentEvent, HermesOffering
from dependencies import _get_user_id, _write_audit_log, _hash_api_key
from hermes import _utcnow, _validate_skill_options


# ── Pydantic models ─────────────────────────────────────────────

class SkillAttach(BaseModel):
    skill_id: str
    options: dict[str, Any] = {}


class SkillUpdate(BaseModel):
    options: dict[str, Any] | None = None
    enabled: bool | None = None


class AgentReportItem(BaseModel):
    skill_id: str
    state: str  # 'installed' | 'failed' | 'removed'
    error: str | None = None


class AgentReport(BaseModel):
    version: int
    results: list[AgentReportItem] = []


# ══════════════════════════════════════════════════════════════════
# Servers
# ══════════════════════════════════════════════════════════════════

async def _load_owned_server(session, server_id: int, uid: int) -> HermesServer | None:
    res = await session.execute(select(HermesServer).where(HermesServer.id == server_id))
    server = res.scalar_one_or_none()
    if not server or server.user_id != uid:
        return None
    return server


@hermes.router.get('/hermes/servers')
async def list_servers(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
    async with async_session() as session:
        res = await session.execute(
            select(HermesServer).where(HermesServer.user_id == uid).order_by(HermesServer.created_at.desc())
        )
        servers = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder([_server_public(s) for s in servers]))


def _server_public(server: HermesServer) -> dict:
    """Server shape safe to return to the owning user -- no token hash."""
    return {
        'id': server.id, 'order_id': server.order_id, 'offering_id': server.offering_id,
        'hostname': server.hostname, 'ip_address': server.ip_address, 'ssh_port': server.ssh_port,
        'region': server.region, 'status': server.status,
        'monthly_price_irt': server.monthly_price_irt, 'paid_through_at': server.paid_through_at,
        'agent_token_prefix': server.agent_token_prefix,
        'desired_state_version': server.desired_state_version,
        'applied_state_version': server.applied_state_version,
        'in_sync': server.desired_state_version == server.applied_state_version,
        'last_heartbeat_at': server.last_heartbeat_at, 'agent_version': server.agent_version,
        'created_at': server.created_at,
    }


@hermes.router.get('/hermes/servers/{server_id}')
async def get_server(request: Request, server_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return err('سرور یافت نشد', 'Server not found', 404)
        skills_res = await session.execute(
            select(HermesServerSkill).where(HermesServerSkill.server_id == server.id)
        )
        skills = [row[0] for row in skills_res.fetchall()]

    data = _server_public(server)
    data['skills'] = jsonable_encoder(skills)
    return JSONResponse(jsonable_encoder(data))


@hermes.router.post('/hermes/servers/{server_id}/skills')
async def attach_skill(request: Request, server_id: int, payload: SkillAttach) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)

    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return err('سرور یافت نشد', 'Server not found', 404)

        skill_res = await session.execute(
            select(HermesSkillCatalog).where(HermesSkillCatalog.id == payload.skill_id, HermesSkillCatalog.active == True)
        )
        skill = skill_res.scalar_one_or_none()
        if not skill:
            return err('اسکیل یافت نشد', 'Skill not found', 404)

        error = _validate_skill_options(skill.options_schema, payload.options)
        if error:
            return err(error[0], error[1], 400)

        offering_res = await session.execute(select(HermesOffering).where(HermesOffering.id == server.offering_id))
        offering = offering_res.scalar_one_or_none()

        existing_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.enabled == True
            )
        )
        existing_count = len(existing_res.fetchall())
        if offering and existing_count >= offering.max_skills:
            return err(
                f'این سرور حداکثر {offering.max_skills} اسکیل پشتیبانی می‌کند',
                f'This server supports at most {offering.max_skills} skills',
                400,
            )

        dup_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == payload.skill_id
            )
        )
        if dup_res.scalar_one_or_none():
            return err('این اسکیل قبلاً روی سرور نصب شده است', 'This skill is already installed on the server', 400)

        row = HermesServerSkill(
            server_id=server.id, skill_id=payload.skill_id, options=payload.options,
            enabled=True, state='pending',
        )
        session.add(row)
        server.desired_state_version += 1
        server.updated_at = _utcnow()
        await session.commit()

    return JSONResponse({'status': 'ok', 'desired_state_version': server.desired_state_version})


@hermes.router.put('/hermes/servers/{server_id}/skills/{skill_id}')
async def update_skill(request: Request, server_id: int, skill_id: str, payload: SkillUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)

    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return err('سرور یافت نشد', 'Server not found', 404)

        row_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == skill_id
            )
        )
        row = row_res.scalar_one_or_none()
        if not row:
            return err('اسکیل روی این سرور نصب نیست', 'Skill is not installed on this server', 404)

        if payload.options is not None:
            catalog_res = await session.execute(select(HermesSkillCatalog).where(HermesSkillCatalog.id == skill_id))
            catalog = catalog_res.scalar_one_or_none()
            error = _validate_skill_options(catalog.options_schema if catalog else {}, payload.options)
            if error:
                return err(error[0], error[1], 400)
            row.options = payload.options
        if payload.enabled is not None:
            row.enabled = payload.enabled

        row.state = 'pending'
        row.updated_at = _utcnow()
        server.desired_state_version += 1
        server.updated_at = _utcnow()
        await session.commit()

    return JSONResponse({'status': 'ok', 'desired_state_version': server.desired_state_version})


@hermes.router.delete('/hermes/servers/{server_id}/skills/{skill_id}')
async def remove_skill(request: Request, server_id: int, skill_id: str) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)

    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return err('سرور یافت نشد', 'Server not found', 404)

        row_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == skill_id
            )
        )
        row = row_res.scalar_one_or_none()
        if not row:
            return err('اسکیل روی این سرور نصب نیست', 'Skill is not installed on this server', 404)

        # Not deleted immediately -- the agent must confirm removal via
        # POST /hermes/agent/report before the row disappears.
        row.state = 'removing'
        row.enabled = False
        row.updated_at = _utcnow()
        server.desired_state_version += 1
        server.updated_at = _utcnow()
        await session.commit()

    return JSONResponse({'status': 'ok', 'desired_state_version': server.desired_state_version})


@hermes.router.post('/hermes/servers/{server_id}/rotate-agent-token')
async def rotate_agent_token(request: Request, server_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)

    raw_token = f'hsa-{secrets.token_urlsafe(32)}'
    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return err('سرور یافت نشد', 'Server not found', 404)
        server.agent_token_hash = _hash_api_key(raw_token)
        server.agent_token_prefix = raw_token[:12]
        server.updated_at = _utcnow()
        await session.commit()

    await _write_audit_log('hermes.server.rotate_agent_token', target_type='hermes_server', target_id=server_id, request=request)
    return JSONResponse({'status': 'ok', 'agent_token': raw_token})


# ══════════════════════════════════════════════════════════════════
# Agent daemon endpoints (token auth, not session cookie)
# ══════════════════════════════════════════════════════════════════

async def _authenticate_agent(request: Request) -> HermesServer | JSONResponse:
    """Resolve the calling server from its `Authorization: Bearer hsa-...`
    token. Returns the HermesServer row, or a ready-to-return 401
    JSONResponse on failure -- callers check the type."""
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not token or not token.startswith('hsa-'):
        return err('توکن نامعتبر است', 'Invalid token', 401)
    token_hash = _hash_api_key(token)
    async with async_session() as session:
        res = await session.execute(select(HermesServer).where(HermesServer.agent_token_hash == token_hash))
        server = res.scalar_one_or_none()
        if not server or server.status == 'terminated':
            return err('توکن نامعتبر است', 'Invalid token', 401)
        return server


@hermes.router.get('/hermes/agent/state')
async def agent_state(request: Request) -> JSONResponse:
    server = await _authenticate_agent(request)
    if isinstance(server, JSONResponse):
        return server

    async with async_session() as session:
        skills_res = await session.execute(
            select(HermesServerSkill, HermesSkillCatalog).join(
                HermesSkillCatalog, HermesServerSkill.skill_id == HermesSkillCatalog.id
            ).where(HermesServerSkill.server_id == server.id)
        )
        rows = skills_res.fetchall()

        db_server = await session.get(HermesServer, server.id)
        db_server.last_heartbeat_at = _utcnow()
        agent_version = request.headers.get('X-Agent-Version')
        if agent_version:
            db_server.agent_version = agent_version
        await session.commit()

    skills = [{
        'id': skill_row.skill_id, 'manifest': catalog_row.manifest,
        'options': skill_row.options, 'enabled': skill_row.enabled,
    } for skill_row, catalog_row in rows]

    return JSONResponse(jsonable_encoder({'version': server.desired_state_version, 'skills': skills}))


@hermes.router.post('/hermes/agent/report')
async def agent_report(request: Request, payload: AgentReport) -> JSONResponse:
    server = await _authenticate_agent(request)
    if isinstance(server, JSONResponse):
        return server

    async with async_session() as session:
        db_server = await session.get(HermesServer, server.id)
        for item in payload.results:
            row_res = await session.execute(
                select(HermesServerSkill).where(
                    HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == item.skill_id
                )
            )
            row = row_res.scalar_one_or_none()
            if not row:
                continue
            if item.state == 'removed':
                await session.delete(row)
            else:
                row.state = item.state
                row.error = item.error
                row.updated_at = _utcnow()

        db_server.applied_state_version = payload.version
        db_server.last_heartbeat_at = _utcnow()
        session.add(HermesAgentEvent(
            server_id=server.id, event='report',
            detail={'version': payload.version, 'results': [r.model_dump() for r in payload.results]},
        ))
        await session.commit()

    return JSONResponse({'status': 'ok'})
