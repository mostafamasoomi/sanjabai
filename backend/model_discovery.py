"""
Model discovery: keep `model_catalog` in step with what the upstreams offer.

`model_catalog` was populated by hand. When an upstream added or dropped a
model nothing noticed, so the catalog slowly diverged from what the gateway
could actually serve — the same drift that made the hard-coded "working model"
lists wrong.

This module reads `GET /v1/models` from every configured provider and upserts
what it finds. Two rules keep it safe to run unattended:

  * Rows an admin curated (`provenance = 'admin-approved'`) are never
    overwritten. Discovery only fills in models nobody has decided about.
  * Discovery never sets pricing. A model with no price is inserted as
    `maintenance` so it is visible in the admin UI but not offered to users
    until someone prices it. Serving a model we cannot bill for would silently
    give it away.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import sqlalchemy

from database import async_session
from providers import Provider, configured_providers, list_models

logger = logging.getLogger('model_discovery')


def _display_name(model_id: str) -> str:
    """Turn `deepseek-v4-pro` into `Deepseek V4 Pro` as a starting point.

    Only used for models an admin has not named yet; it is a placeholder, not
    an attempt at correct branding.
    """
    bare = model_id.split('/')[-1]
    words = re.split(r'[-_.]+', bare)
    return ' '.join(w.upper() if len(w) <= 2 else w.capitalize() for w in words if w)


def _guess_provider(model_id: str) -> str:
    """Best-effort vendor from the id, for grouping in the picker."""
    bare = model_id.lower()
    if '/' in model_id:
        return model_id.split('/')[0].lower()
    for token, vendor in (
        ('gpt-oss', 'openai'), ('gpt', 'openai'), ('o1', 'openai'),
        ('claude', 'anthropic'),
        ('gemini', 'google'), ('gemma', 'google'),
        ('llama', 'meta'),
        ('mistral', 'mistral'), ('mixtral', 'mistral'),
        ('deepseek', 'deepseek'),
        ('qwen', 'qwen'),
        ('kimi', 'moonshot'),
        ('mimo', 'xiaomi'),
        ('tencent', 'tencent'), ('hy', 'tencent'),
        ('grok', 'xai'),
    ):
        if token in bare:
            return vendor
    return 'other'


def _context_window(raw: dict[str, Any]) -> int:
    """Context window if the upstream reports one, else a conservative default.

    The column is NOT NULL with a positive check, so a default is required;
    8k is low enough that it will look obviously provisional in the admin UI.
    """
    for key in ('context_window', 'context_length', 'max_context_tokens', 'max_input_tokens'):
        value = raw.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return 8192


async def sync_provider(p: Provider) -> dict[str, Any]:
    """Upsert every model one provider reports. Returns a small summary."""
    if async_session is None:
        return {'provider': p.name, 'error': 'no_db'}

    models = await list_models(p)
    if not models:
        return {'provider': p.name, 'seen': 0, 'inserted': 0, 'skipped': 0}

    inserted = 0
    async with async_session() as session:
        for raw in models:
            model_id = str(raw.get('id') or '').strip()
            if not model_id:
                continue
            # Embeddings and rerankers are not chat models; offering them in a
            # chat picker would just produce confusing errors.
            if 'embedding' in model_id.lower() or 'rerank' in model_id.lower():
                continue

            result = await session.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO model_catalog
                        (id, provider_model_id, provider, display_name, context_window,
                         availability, provenance, upstream, last_verified_at)
                    VALUES
                        (:id, :pmid, :prov, :name, :ctx,
                         'maintenance', 'provider', :upstream, now())
                    ON CONFLICT (id) DO UPDATE SET
                        upstream         = EXCLUDED.upstream,
                        last_verified_at = now()
                      WHERE model_catalog.provenance <> 'admin-approved'
                    """
                ),
                {
                    'id': model_id,
                    'pmid': model_id,
                    'prov': _guess_provider(model_id),
                    'name': _display_name(model_id),
                    'ctx': _context_window(raw),
                    'upstream': p.name,
                },
            )
            if result.rowcount:
                inserted += 1
        await session.commit()

    return {
        'provider': p.name,
        'seen': len(models),
        'inserted': inserted,
        'skipped': len(models) - inserted,
    }


async def sync_all() -> list[dict[str, Any]]:
    """Discover across every configured provider."""
    out = []
    for p in configured_providers():
        try:
            out.append(await sync_provider(p))
        except Exception as e:
            logger.warning('discovery failed for %s: %s', p.name, e)
            out.append({'provider': p.name, 'error': type(e).__name__})
    return out
