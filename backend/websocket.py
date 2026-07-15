"""
WebSocket endpoint for real-time notifications.
"""
from __future__ import annotations

import asyncio as aio
import json
import logging as _logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from dependencies import _get_session_user_id, _ws_clients

router = APIRouter()


@router.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    """Real-time connection for notifications and usage updates"""
    await ws.accept()

    token = ''
    auth_header = ws.headers.get('authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    if not token:
        token = ws.query_params.get('token', '')
        if token:
            _logging.getLogger(__name__).warning(
                'WebSocket auth via query param is deprecated and insecure. '
                'Clients should send token as first message after connect.'
            )
    if not token:
        try:
            first_msg = await aio.wait_for(ws.receive_text(), timeout=10)
            if first_msg.startswith('auth:'):
                token = first_msg[5:]
        except (aio.TimeoutError, Exception):
            pass

    uid = _get_session_user_id(token) if token else None

    if not uid:
        await ws.send_json({'type': 'error', 'message': 'unauthorized | لطفا وارد حساب خود شوید'})
        await ws.close()
        return

    _ws_clients.setdefault(uid, []).append(ws)

    try:
        while True:
            try:
                data = await aio.wait_for(ws.receive_text(), timeout=30)
                if data == 'ping':
                    await ws.send_json({'type': 'pong'})
            except aio.TimeoutError:
                try:
                    await ws.send_json({'type': 'heartbeat'})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        clients = _ws_clients.get(uid, [])
        if ws in clients:
            clients.remove(ws)
        if not clients:
            _ws_clients.pop(uid, None)
