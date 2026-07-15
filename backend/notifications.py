"""
Notification endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from models import Notification, Quota
from dependencies import _get_user_id, _to_fa

router = APIRouter()


@router.get('/notifications')
async def list_notifications(request: Request) -> JSONResponse:
    """Get user notifications"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        quota_res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
        quota = quota_res.fetchone()
        if quota and quota.daily_limit > 0:
            usage_pct = (quota.used_today / quota.daily_limit) * 100
            if usage_pct >= 80:
                today = datetime.now(timezone.utc).replace(tzinfo=None).date()
                existing = await session.execute(
                    Notification.__table__.select().where(
                        Notification.user_id == uid,
                        Notification.type == 'alert',
                        Notification.title == 'هشدار مصرف',
                    )
                )
                existing_rows = existing.fetchall()
                today_alerts = [r for r in existing_rows if r.created_at.date() == today]
                if not today_alerts:
                    alert = Notification(
                        user_id=uid, type='alert', title='هشدار مصرف',
                        body=f'شما {_to_fa(f"{usage_pct:.0f}")}٪ از سقف مصرف روزانه خود را استفاده کردهاید. ({_to_fa(f"{quota.used_today:,}")} از {_to_fa(f"{quota.daily_limit:,}")} توکن)',
                    )
                    session.add(alert)
                    await session.commit()

        res = await session.execute(
            Notification.__table__.select()
            .where(Notification.user_id == uid)
            .order_by(Notification.created_at.desc())
            .limit(20)
        )
        rows = [
            {
                'id': r.id, 'type': r.type, 'title': r.title, 'body': r.body,
                'read': r.read,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/notifications/{nid}/read')
async def mark_notification_read(request: Request, nid: int) -> JSONResponse:
    """Mark notification as read"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        await session.execute(
            Notification.__table__.update()
            .where(Notification.id == nid, Notification.user_id == uid),
            {'read': True}
        )
        await session.commit()
    return JSONResponse({'status': 'ok'})
