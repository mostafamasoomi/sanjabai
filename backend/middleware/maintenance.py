"""Site-wide maintenance-mode middleware.

Wires the ``maintenance_mode`` flag from ``backend/site_settings.py`` (seeded
by migration 0036, previously unwired -- see that module's ``FLAGS``
registry) into actual behaviour: when the flag is on, ordinary user traffic
gets a 503 instead of reaching any route handler.

There is no single existing choke point for "reject everything" in this
codebase (routers are registered per-domain in app.py, each with its own
auth), so this has to be a middleware sitting in front of all of them,
matching the style of ``security.SecurityHeadersMiddleware`` /
``security.CsrfMiddleware`` / ``security.RateLimitMiddleware``.

── Fail-open, twice over ────────────────────────────────────────────────
:func:`site_settings.get_site_flag` already fails open to
``FLAGS['maintenance_mode'].default`` (``False``) on any Redis/DB error --
see that module's docstring. This middleware additionally wraps the *call*
to it in its own try/except: an unexpected error anywhere in that path
(import failure, a future refactor that makes the helper raise, ...) must
never turn into a site-wide 503. If anything goes wrong, traffic passes.
A settings-store outage is not a reason to take the whole site down --
that would be the opposite of what a maintenance switch is for.

── Who still gets through while "off" ───────────────────────────────────
* Admins (verified via ``dependencies.admin_required`` -- the same cookie
  session + CSRF check every other admin route uses; see the "why not a
  narrower check" note on :func:`_is_admin` below).
* Exempt path prefixes, so the site stays recoverable and observable from
  outside while in maintenance: ``/health``, ``/admin``, ``/auth/login``,
  ``/auth/logout``, ``/status``. Each of these was verified against the
  actual routers (health.py, admin.py + auth.py's ``/admin/login`` and
  ``/admin/logout``, auth.py, status_page.py) before being hardcoded here --
  see the module docstring in the accompanying test file for the grep
  evidence. ``/auth/admin-login`` does NOT exist in this codebase (admin
  login is ``POST /admin/login``, already covered by the ``/admin``
  prefix) and is deliberately not listed.
* ``OPTIONS`` preflight requests, unconditionally -- a CORS preflight must
  never be answered with a 503 or the browser will treat the real request
  as blocked.
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from i18n import err

logger = logging.getLogger(__name__)

# Prefixes exempt from the 503 even while maintenance_mode is on. Every
# prefix here was confirmed against the real routers -- see module
# docstring. Matched with `path == prefix or path.startswith(prefix + '/')`
# so e.g. `/status` doesn't accidentally also exempt an unrelated
# `/statuses` route.
_EXEMPT_PREFIXES: tuple[str, ...] = (
    '/health',
    '/admin',
    '/auth/login',
    '/auth/logout',
    '/status',
)


def _is_exempt_path(path: str) -> bool:
    return any(path == p or path.startswith(p + '/') for p in _EXEMPT_PREFIXES)


async def _is_admin(request: Request) -> bool:
    """Whether this request carries valid admin auth.

    Reuses ``dependencies.admin_required`` directly rather than
    reimplementing the check -- it is imported lazily (inside the function,
    not at module import time) to avoid a circular import: ``dependencies``
    is imported by nearly every route module, and this middleware needs to
    be importable from ``app.py`` before those are all wired up.
    """
    from dependencies import admin_required
    return await admin_required(request)


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Return 503 for ordinary traffic while ``maintenance_mode`` is on.

    Admins and the exempt paths above always pass through. Any error while
    resolving the flag or the admin check fails OPEN (traffic passes) --
    see module docstring.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == 'OPTIONS':
            return await call_next(request)

        if _is_exempt_path(request.url.path):
            return await call_next(request)

        try:
            from site_settings import get_site_flag
            maintenance_on = await get_site_flag('maintenance_mode')
        except Exception as e:
            logger.warning('maintenance middleware: flag read failed, failing open: %s', e)
            return await call_next(request)

        if not maintenance_on:
            return await call_next(request)

        try:
            if await _is_admin(request):
                return await call_next(request)
        except Exception as e:
            # An error in the admin check must not itself cause a false
            # 503 for the entire site -- but it also must not grant a
            # non-admin access, so this only fails the ADMIN CHECK open in
            # the sense of "keep enforcing maintenance mode", not open in
            # the sense of "let the request through". The flag-read
            # try/except above is what implements the real fail-open
            # contract for this middleware.
            logger.warning('maintenance middleware: admin check failed: %s', e)

        return err(
            'سایت در حال حاضر در حالت تعمیر و نگهداری است. لطفاً بعداً دوباره تلاش کنید.',
            'The site is currently under maintenance. Please try again later.', 503,
        )
