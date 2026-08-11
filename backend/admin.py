"""
Admin endpoints — aggregator.

The implementations live in one module per domain (this file used to hold all
of them inline, well past the project's 500-line ceiling):

  admin_catalog.py    – model catalog pricing, availability toggle, live probe
  admin_content.py    – features, discounts, about, proxy, org default model
  admin_users.py      – user list/ban/edit and the per-user detail drill-down
  admin_billing.py    – plans, credit packages, subscriptions
  admin_analytics.py  – CSV exports, dashboard stats, 30-day timeseries
  admin_security.py   – audit logs, TOTP MFA, lockout status
  usage.py            – user-scoped /me/usage endpoints (not admin-gated)

``router`` below aggregates all of them, so ``from admin import router`` keeps
mounting the exact same set of paths it always did.

The domain modules are also re-exported as names on this module. That is not
cosmetic: several tests patch ``admin.admin_required`` to bypass auth, and each
domain module holds its *own* ``from dependencies import admin_required``
binding. ``_patch_admin_required`` below turns ``admin.admin_required`` into a
single knob that forwards to whatever the current value is, so patching it here
still takes effect inside every domain module.
"""
from __future__ import annotations

from fastapi import APIRouter

import admin_analytics
import admin_billing
import admin_catalog
import admin_content
import admin_security
import admin_users
import usage

from dependencies import admin_required as _real_admin_required

# Re-exported for backward compatibility: other modules, scripts and tests
# import these names from `admin` directly.
from admin_users import AdminUserEdit  # noqa: F401
from admin_catalog import get_active_price  # noqa: F401
from admin_security import (  # noqa: F401
    MfaSetupRequest,
    MfaVerifyRequest,
    MfaEnableRequest,
)

_DOMAIN_MODULES = (
    admin_catalog,
    admin_content,
    admin_users,
    admin_billing,
    admin_analytics,
    admin_security,
)


async def admin_required(request):
    """Auth gate for every admin route, indirected through this module.

    Each domain module calls ``admin.admin_required`` (bound at import time by
    the shim installed below) rather than its own imported copy, so patching
    ``admin.admin_required`` — as the test-suite does — reaches all of them.
    """
    return await _real_admin_required(request)


def _patch_admin_required() -> None:
    """Point every domain module's ``admin_required`` at this module's.

    Each module does ``from dependencies import admin_required``, which copies
    the function object into that module's globals. Rebinding those names to a
    forwarder that resolves ``admin.admin_required`` at *call* time means a
    single patch of ``admin.admin_required`` covers all of them, preserving the
    pre-split behaviour where there was only one binding to patch.
    """
    import sys

    _self = sys.modules[__name__]

    async def _forward(request):
        return await _self.admin_required(request)

    for mod in _DOMAIN_MODULES:
        mod.admin_required = _forward


_patch_admin_required()


router = APIRouter()
for _mod in _DOMAIN_MODULES:
    router.include_router(_mod.router)
router.include_router(usage.router)
del _mod
