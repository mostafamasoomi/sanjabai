"""
Admin endpoints aggregator.

Historically a single ~1,864-line file covering user management, pricing,
features, discounts, about, proxy config, org default model, analytics,
stats, plans, credit packages, subscriptions, data export, `/me/usage*`,
admin MFA and lockout management. Split (house 500-line cap) into one
module per section, following the same aggregator pattern already used by
chat.py/chat_web.py (see chat.py's module docstring):

  admin_pricing.py    -- /admin/pricing, /admin/models/*/toggle|test
  admin_content.py    -- Features, Discounts, About, Proxy Config,
                          org-default-model
  admin_users.py      -- User management + per-user detail endpoints
  admin_analytics.py  -- Data export, analytics/stats, timeseries, audit log
  admin_plans.py      -- Plans, credit packages, subscriptions
  admin_usage_me.py   -- /me/usage* (NOT admin-only -- a regular logged-in
                          user's own usage summary)
  admin_mfa.py         -- Admin MFA (TOTP) skeleton + lockout management

IMPORT CONTRACT: no production module or test imports any symbol from
`admin` other than `router` (grepped: app.py:314 `from admin import router
as admin_router`, tests/test_verification.py and tests/test_quick_verify.py
`from admin import router`) -- with ONE deliberate exception:
`admin.admin_required`.

MONKEYPATCH CONTRACT for `admin_required`: tests/test_admin_model_control.py
and tests/test_credit_package_model_label.py do `patch('admin.admin_required',
...)` -- a string-target patch that only takes effect on code that reads
`admin.admin_required` as an attribute at call time, not on code that
captured the function via `from dependencies import admin_required` into
its own module namespace. Before the split, every admin route lived
directly in this file and shared this one module-level import, so any test
patching `admin.admin_required` transparently gated every route. To keep
that behaviour, `admin_required` is imported here (making it a patchable
attribute of THIS module) and every admin_*.py module below that gates a
route on it reaches it through `admin.admin_required(request)` at call
time -- via a plain `import admin`, never `from admin import admin_required`
-- exactly the chat.py/chat_web.py pattern (see chat.py's module docstring).
`import admin` inside those modules is safe against the circular import the
same way chat_web.py's `import chat` is: nothing touches `admin.<attr>`
until a request handler actually runs, by which point this file has
finished executing (it only calls `include_router`, never an admin_*.py
function, at import time). `admin_usage_me.py` is the one section module
that does NOT need this -- its routes gate on `_get_user_id`, not
`admin_required`, since `/me/usage*` is a regular user endpoint, not admin.

Everything else here stays a *pure* aggregator: each admin_*.py module is
otherwise self-contained and imports what it needs directly from
database/models/dependencies/security, not through this file. Do not add
logic here -- if a new admin endpoint doesn't fit an existing section
module, give it its own new admin_*.py module and `include_router` it
below, keeping this file thin.
"""
from __future__ import annotations

from fastapi import APIRouter

from dependencies import admin_required  # noqa: F401 -- see MONKEYPATCH CONTRACT above

from admin_pricing import router as _pricing_router
from admin_content import router as _content_router
from admin_users import router as _users_router
from admin_analytics import router as _analytics_router
from admin_plans import router as _plans_router
from admin_usage_me import router as _usage_me_router
from admin_mfa import router as _mfa_router
from admin_security import router as _security_router

router = APIRouter()

router.include_router(_pricing_router)
router.include_router(_content_router)
router.include_router(_users_router)
router.include_router(_analytics_router)
router.include_router(_plans_router)
router.include_router(_usage_me_router)
router.include_router(_mfa_router)
router.include_router(_security_router)
