"""
Admin panel — aggregator.

The implementations live in one module per domain (this file used to hold all
of them inline, well past the project's 500-line ceiling):

  admin_auth.py        – login, logout, session management
  admin_dashboard.py   – dashboard page and stats API
  admin_pricing.py     – pricing, model catalog, toggle/test
  admin_users.py       – users page and user management API
  admin_usage.py       – usage page and global usage analytics API
  admin_conversations.py – conversations page and API
  admin_payments.py    – payments page and API
  admin_api_keys.py    – API keys page and API
  admin_audit.py       – audit logs page and API
  admin_notifications.py – notifications page and API
  admin_content.py     – features, discounts, about, proxy config
  admin_health.py      – health endpoint

``app`` below aggregates all of them, so importing this module keeps
mounting the exact same set of paths it always did.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import admin_auth
import admin_dashboard
import admin_pricing
import admin_users
import admin_usage
import admin_conversations
import admin_payments
import admin_api_keys
import admin_audit
import admin_notifications
import admin_content
import admin_health
import admin_config

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------
app = FastAPI(title='MultiAPI Admin')
app.mount('/static', StaticFiles(directory='/app/static'), name='static')

# ---------------------------------------------------------------------------
# Register all routers
# ---------------------------------------------------------------------------
_domain_modules = (
    admin_auth,
    admin_dashboard,
    admin_pricing,
    admin_users,
    admin_usage,
    admin_conversations,
    admin_payments,
    admin_api_keys,
    admin_audit,
    admin_notifications,
    admin_content,
    admin_health,
)

for _mod in _domain_modules:
    app.include_router(_mod.router)
del _mod