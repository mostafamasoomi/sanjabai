"""Admin MFA (TOTP) skeleton and lockout-status management.

Split out of admin.py (house 500-line cap) -- see admin.py's module
docstring for the full split map. Pure move: no behaviour change.

MONKEYPATCH CONTRACT: routes here gate on `admin.admin_required(request)`
(via a plain `import admin`, never `from admin import admin_required`) --
see admin.py's own module docstring for why.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import admin
from dependencies import _write_audit_log, ADMIN_COOKIE_NAME
from security import get_lockout_info

router = APIRouter()


# ── Admin MFA (TOTP) Skeleton ───────────────────────────────────

class MfaSetupRequest(BaseModel):
    """Empty body – the endpoint generates a new TOTP secret."""
    pass

class MfaVerifyRequest(BaseModel):
    code: str

class MfaEnableRequest(BaseModel):
    code: str
    secret: str


@router.post('/admin/mfa/setup')
async def admin_mfa_setup(request: Request) -> JSONResponse:
    """Generate a new TOTP secret and provisioning URI for the admin.

    Returns the secret and a otpauth:// URI that can be rendered as a QR
    code client-side.  The secret is NOT stored yet – it is stored only
    after the admin verifies a valid TOTP code via /admin/mfa/enable.
    """
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        import pyotp
    except ImportError:
        return JSONResponse({'detail': 'TOTP library not installed'}, status_code=500)

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name='Sanjabai Admin',
        issuer_name='Sanjabai',
    )

    # Store the pending secret in Redis so we can verify it later
    try:
        from database import rds
        pending_key = f'mfa_pending:{request.cookies.get(ADMIN_COOKIE_NAME, "unknown")}'
        await rds.setex(pending_key, 300, secret)  # 5 min to complete setup
    except Exception:
        pass

    return JSONResponse({
        'secret': secret,
        'provisioning_uri': provisioning_uri,
        'expires_in': 300,
    })


@router.post('/admin/mfa/enable')
async def admin_mfa_enable(request: Request, payload: MfaEnableRequest) -> JSONResponse:
    """Verify TOTP code and enable MFA for the admin user.

    The admin must have completed /admin/mfa/setup first.
    After verification the secret is stored in the users table.
    """
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        import pyotp
    except ImportError:
        return JSONResponse({'detail': 'TOTP library not installed'}, status_code=500)

    # Retrieve the pending secret
    try:
        from database import rds
        pending_key = f'mfa_pending:{request.cookies.get(ADMIN_COOKIE_NAME, "unknown")}'
        pending_secret = await rds.get(pending_key)
    except Exception:
        pending_secret = None

    secret = payload.secret or pending_secret
    if not secret:
        return JSONResponse({'detail': 'TOTP secret not found. Run setup first.'}, status_code=400)

    # Verify the code
    totp = pyotp.TOTP(secret)
    if not totp.verify(payload.code, valid_window=1):
        return JSONResponse({'detail': 'کد TOTP نامعتبر است'}, status_code=400)

    # Store the secret (would need user_id from admin session; for skeleton, store in Redis)
    try:
        from database import rds
        admin_sid = request.cookies.get(ADMIN_COOKIE_NAME, '')
        mfa_key = f'admin_mfa:{admin_sid}'
        await rds.setex(mfa_key, 86400 * 30, secret)  # 30 day storage
        # Mark session as MFA-enabled
        sess_key = f'admin_session:{admin_sid}'
        sess_raw = await rds.get(sess_key)
        if sess_raw:
            import json
            sess = json.loads(sess_raw)
            sess['totp_enabled'] = True
            from dependencies import ADMIN_SESSION_TTL
            await rds.setex(sess_key, ADMIN_SESSION_TTL, json.dumps(sess))
        # Cleanup pending
        await rds.delete(pending_key)
    except Exception:
        pass

    await _write_audit_log('admin.mfa.enabled', request=request)
    return JSONResponse({'status': 'ok', 'message': 'TOTP MFA فعال شد'})


@router.post('/admin/mfa/verify')
async def admin_mfa_verify(request: Request, payload: MfaVerifyRequest) -> JSONResponse:
    """Verify a TOTP code and mark the current session as verified.

    Called after login when MFA is enabled but the session is not yet verified.
    """
    if not await admin.admin_required(request):
        # Even if admin_required fails due to totp_required, we still need to
        # check for the admin session cookie directly
        sid = request.cookies.get(ADMIN_COOKIE_NAME, '')
        if not sid:
            return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
        try:
            from database import rds as _rds
            mfa_key = f'admin_mfa:{sid}'
            secret = await _rds.get(mfa_key)
            if not secret:
                return JSONResponse({'detail': 'TOTP فعال نیست'}, status_code=400)

            import pyotp
            totp = pyotp.TOTP(secret)
            if not totp.verify(payload.code, valid_window=1):
                return JSONResponse({'detail': 'کد TOTP نامعتبر است'}, status_code=400)

            # Mark session as TOTP verified
            sess_key = f'admin_session:{sid}'
            sess_raw = await _rds.get(sess_key)
            if sess_raw:
                import json
                sess = json.loads(sess_raw)
                sess['totp_verified'] = True
                from dependencies import ADMIN_SESSION_TTL
                await _rds.setex(sess_key, ADMIN_SESSION_TTL, json.dumps(sess))

            await _write_audit_log('admin.mfa.verified', request=request)
            return JSONResponse({'status': 'ok'})
        except Exception:
            return JSONResponse({'detail': 'خطای سرور'}, status_code=500)

    # If admin_required passed (MFA not enabled or already verified)
    return JSONResponse({'status': 'ok', 'message': 'TOTP از قبل تأیید شده'})


@router.post('/admin/mfa/disable')
async def admin_mfa_disable(request: Request) -> JSONResponse:
    """Disable TOTP MFA for the admin session."""
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        from database import rds as _rds
        admin_sid = request.cookies.get(ADMIN_COOKIE_NAME, '')
        mfa_key = f'admin_mfa:{admin_sid}'
        await _rds.delete(mfa_key)
        # Update session to disable MFA
        sess_key = f'admin_session:{admin_sid}'
        sess_raw = await _rds.get(sess_key)
        if sess_raw:
            import json
            sess = json.loads(sess_raw)
            sess['totp_enabled'] = False
            sess['totp_verified'] = False
            from dependencies import ADMIN_SESSION_TTL
            await _rds.setex(sess_key, ADMIN_SESSION_TTL, json.dumps(sess))
    except Exception:
        pass

    await _write_audit_log('admin.mfa.disabled', request=request)
    return JSONResponse({'status': 'ok'})


# ── Lockout Management ──────────────────────────────────────────

@router.get('/admin/lockout/status')
async def admin_lockout_status(request: Request) -> JSONResponse:
    """Check lockout status for a given identifier (admin only)."""
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    identifier = request.query_params.get('identifier', '')
    if not identifier:
        return JSONResponse({'detail': 'identifier parameter required'}, status_code=400)

    info = await get_lockout_info(identifier)
    return JSONResponse(info)
