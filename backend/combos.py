"""
User model combo endpoints: CRUD for a user's own ordered list of models
that services/smart_router.py will try in turn.

Schema is backend/migrations/0050_user_model_combos.sql -- read its header
comment before touching this file, it is the contract. The short version:
`user_model_combo_item.model_public_id` stores the PUBLIC id the user picked
(`sanjab/...`), never a provider route or `provider_model_id` -- a normal
user must never see a provider or upstream route, and this module never
echoes one back.

`import chat` (not `from chat import ...`) deliberately, so
`chat._resolve_public_model` / `chat._is_model_allowed` are read through the
module each call -- late-bound the same way document_generator.py and the
other chat_*.py siblings do it, so a test's `patch.object(chat, ...)` or
`patch('chat._is_model_allowed', ...)` actually takes effect here too.
"""
from __future__ import annotations

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import chat
from database import async_session
from dependencies import _get_user_id
from i18n import err

router = APIRouter()

_MAX_COMBOS_PER_USER = 10
_MIN_ITEMS = 2
_MAX_ITEMS = 5
_VALID_POLICIES = ('sequential', 'round_robin')


class ComboItemIn(BaseModel):
    model_public_id: str
    # Accepted so a client can round-trip the same shape it reads back, but
    # deliberately ignored on write -- see _insert_items. The server assigns
    # position from submission order (0, 1, 2, ...), never from this field.
    position: int | None = None


class ComboCreate(BaseModel):
    name: str
    policy: str = 'sequential'
    enabled: bool = True
    items: list[ComboItemIn]


class ComboUpdate(BaseModel):
    name: str | None = None
    policy: str | None = None
    enabled: bool | None = None
    items: list[ComboItemIn] | None = None


# ── Validation helpers ──────────────────────────────────────────────────

def _validate_name(name: str) -> JSONResponse | None:
    if not (1 <= len(name) <= 60):
        return err(
            'نام ترکیب باید بین ۱ تا ۶۰ نویسه باشد',
            'Combo name must be between 1 and 60 characters.',
            400,
        )
    return None


def _validate_policy(policy: str) -> JSONResponse | None:
    if policy not in _VALID_POLICIES:
        return err(
            f'سیاست ترکیب باید یکی از این‌ها باشد: {", ".join(_VALID_POLICIES)}',
            f'Combo policy must be one of: {", ".join(_VALID_POLICIES)}.',
            400,
        )
    return None


async def _validate_items(items: list[ComboItemIn]) -> JSONResponse | None:
    """Bounds, duplicates, then per-item resolve + servability -- in that
    order, so a too-short/too-long or duplicated list is rejected before
    spending a DB round trip per item on chat._resolve_public_model /
    chat._is_model_allowed."""
    if not (_MIN_ITEMS <= len(items) <= _MAX_ITEMS):
        return err(
            f'هر ترکیب باید بین {_MIN_ITEMS} تا {_MAX_ITEMS} مدل داشته باشد',
            f'A combo must have between {_MIN_ITEMS} and {_MAX_ITEMS} models.',
            400,
        )
    ids = [it.model_public_id for it in items]
    if len(set(ids)) != len(ids):
        return err(
            'یک مدل نمی‌تواند دو بار در یک ترکیب باشد',
            'A model cannot appear twice in the same combo.',
            400,
        )
    for mid in ids:
        resolved = await chat._resolve_public_model(mid)
        if not await chat._is_model_allowed(resolved):
            return err(
                f'مدل «{mid}» یافت نشد یا در حال حاضر قابل ارائه نیست',
                f'Model "{mid}" was not found or is not currently servable.',
                400,
            )
    return None


async def _insert_items(session, combo_id: int, items: list[ComboItemIn]) -> None:
    """Positions come from enumerate() -- the submitted list order -- never
    from `item.position`. That field is accepted on the wire and ignored
    here on purpose; see ComboItemIn's docstring."""
    for position, it in enumerate(items):
        await session.execute(
            sqlalchemy.text(
                'INSERT INTO user_model_combo_item (combo_id, position, model_public_id) '
                'VALUES (:combo_id, :position, :model_public_id)'
            ),
            {'combo_id': combo_id, 'position': position, 'model_public_id': it.model_public_id},
        )


async def _fetch_combo(session, combo_id: int, uid: int):
    """Ownership check + fetch in one statement: the WHERE clause filters on
    BOTH id and user_id, so a combo owned by someone else comes back as
    `None` -- identical to an id that does not exist at all. Callers must
    turn a `None` into a 404, never a 403, so existence of another user's
    combo is never observable."""
    res = await session.execute(
        sqlalchemy.text(
            'SELECT id, name, policy, enabled, created_at, updated_at '
            'FROM user_model_combo WHERE id = :id AND user_id = :uid'
        ),
        {'id': combo_id, 'uid': uid},
    )
    return res.fetchone()


async def _fetch_items(session, combo_id: int) -> list[dict]:
    res = await session.execute(
        sqlalchemy.text(
            'SELECT position, model_public_id FROM user_model_combo_item '
            'WHERE combo_id = :id ORDER BY position'
        ),
        {'id': combo_id},
    )
    return [{'position': r.position, 'model_public_id': r.model_public_id} for r in res.fetchall()]


def _combo_dict(row, items: list[dict]) -> dict:
    return {
        'id': row.id,
        'name': row.name,
        'policy': row.policy,
        'enabled': row.enabled,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
        'items': items,
    }


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get('/me/combos')
async def list_combos(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                'SELECT c.id AS combo_id, c.name, c.policy, c.enabled, c.created_at, c.updated_at, '
                'i.position, i.model_public_id '
                'FROM user_model_combo c '
                'LEFT JOIN user_model_combo_item i ON i.combo_id = c.id '
                'WHERE c.user_id = :uid '
                'ORDER BY c.id, i.position'
            ),
            {'uid': uid},
        )
        rows = res.fetchall()

    combos: dict[int, dict] = {}
    order: list[int] = []
    for r in rows:
        if r.combo_id not in combos:
            combos[r.combo_id] = {
                'id': r.combo_id, 'name': r.name, 'policy': r.policy, 'enabled': r.enabled,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'updated_at': r.updated_at.isoformat() if r.updated_at else None,
                'items': [],
            }
            order.append(r.combo_id)
        if r.position is not None and r.model_public_id is not None:
            combos[r.combo_id]['items'].append({'position': r.position, 'model_public_id': r.model_public_id})

    return JSONResponse({'combos': [combos[i] for i in order]})


@router.post('/me/combos')
async def create_combo(request: Request, payload: ComboCreate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    name = payload.name.strip()
    name_err = _validate_name(name)
    if name_err:
        return name_err
    policy_err = _validate_policy(payload.policy)
    if policy_err:
        return policy_err
    items_err = await _validate_items(payload.items)
    if items_err:
        return items_err

    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) AS c FROM user_model_combo WHERE user_id = :uid'),
            {'uid': uid},
        )
        count_row = count_res.fetchone()
        if count_row is not None and count_row.c >= _MAX_COMBOS_PER_USER:
            return err(
                f'حداکثر {_MAX_COMBOS_PER_USER} ترکیب برای هر کاربر مجاز است',
                f'At most {_MAX_COMBOS_PER_USER} combos are allowed per user.',
                400,
            )

        try:
            insert_res = await session.execute(
                sqlalchemy.text(
                    'INSERT INTO user_model_combo (user_id, name, policy, enabled) '
                    'VALUES (:uid, :name, :policy, :enabled) '
                    'RETURNING id, name, policy, enabled, created_at, updated_at'
                ),
                {'uid': uid, 'name': name, 'policy': payload.policy, 'enabled': payload.enabled},
            )
            row = insert_res.fetchone()
            await _insert_items(session, row.id, payload.items)
            await session.commit()
        except sqlalchemy.exc.IntegrityError:
            return err('ترکیبی با این نام از قبل وجود دارد', 'A combo with this name already exists.', 400)

    items_out = [{'position': i, 'model_public_id': it.model_public_id} for i, it in enumerate(payload.items)]
    return JSONResponse(_combo_dict(row, items_out), status_code=201)


@router.put('/me/combos/{combo_id}')
async def update_combo(request: Request, combo_id: int, payload: ComboUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        current = await _fetch_combo(session, combo_id, uid)
        if current is None:
            return err('ترکیب یافت نشد', 'Combo not found.', 404)

        name = current.name
        if payload.name is not None:
            name = payload.name.strip()
            name_err = _validate_name(name)
            if name_err:
                return name_err

        policy = current.policy
        if payload.policy is not None:
            policy_err = _validate_policy(payload.policy)
            if policy_err:
                return policy_err
            policy = payload.policy

        enabled = current.enabled if payload.enabled is None else payload.enabled

        if payload.items is not None:
            items_err = await _validate_items(payload.items)
            if items_err:
                return items_err

        try:
            await session.execute(
                sqlalchemy.text(
                    'UPDATE user_model_combo SET name = :name, policy = :policy, enabled = :enabled, '
                    'updated_at = now() WHERE id = :id AND user_id = :uid'
                ),
                {'name': name, 'policy': policy, 'enabled': enabled, 'id': combo_id, 'uid': uid},
            )
            if payload.items is not None:
                await session.execute(
                    sqlalchemy.text('DELETE FROM user_model_combo_item WHERE combo_id = :id'),
                    {'id': combo_id},
                )
                await _insert_items(session, combo_id, payload.items)
            await session.commit()
        except sqlalchemy.exc.IntegrityError:
            return err('ترکیبی با این نام از قبل وجود دارد', 'A combo with this name already exists.', 400)

        row = await _fetch_combo(session, combo_id, uid)
        items_out = await _fetch_items(session, combo_id)

    return JSONResponse(_combo_dict(row, items_out))


@router.delete('/me/combos/{combo_id}')
async def delete_combo(request: Request, combo_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        current = await _fetch_combo(session, combo_id, uid)
        if current is None:
            return err('ترکیب یافت نشد', 'Combo not found.', 404)

        await session.execute(
            sqlalchemy.text('DELETE FROM user_model_combo WHERE id = :id AND user_id = :uid'),
            {'id': combo_id, 'uid': uid},
        )
        await session.commit()

    return JSONResponse({'status': 'deleted'})
