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

import functools
import json
import logging
import os
import pathlib
import re
from typing import Any

import sqlalchemy

from database import async_session
from model_modalities import derive_modalities
from provider_catalog import cached_provider_models
from providers import Provider, configured_providers

logger = logging.getLogger('model_discovery')


# Aggregator/reseller tokens that must never reach a user-facing name -- see
# the standing rule that the ordinary user must never learn which upstream
# serves a model. Only tokens confirmed to be OUR OWN routing/reseller
# identifiers are listed here (proven by appearing fused into a raw model id,
# e.g. `openrouter_gpt_4_o`). Deliberately NOT listed: `omni`, `agnes`,
# `antigravity` -- each also appears as a genuine fragment of a real upstream
# model name in this catalog (NVIDIA "Nemotron ... Omni", Xiaomi "MiMo ...
# Omni", Google's own "antigravity-preview" id, and an unconfirmed-but-
# plausible "Agnes" brand from a reseller) and stripping them blindly would
# mangle a real product name instead of hiding a provider.
_INFRA_TOKENS = frozenset({
    'router', '9router', 'ninerouter', 'omniroute', 'freellmapi', 'bynara',
    'bynaraa2', 'cloudflare', 'opencode', 'horde', 'openrouter', 'tllm',
    'ddgw', 'nothink',
})


# Upstream route prefixes permanently banned from the catalog (owner decision
# 2026-08-30, see docs/ROADMAP.md): a set of free/reseller routes that were
# purged once and must never be re-landed by a discovery sweep.
#
# The prefixes are supply-chain identifiers and this repo is PUBLIC, so they are
# NOT written into tracked source. They load from the DISCOVERY_DENYLIST_PREFIXES
# env var (comma- or newline-separated), or failing that from the gitignored
# `discovery_denylist.txt` beside this module (one prefix per line, `#` comments
# allowed). When neither is configured the set is empty, so a misconfigured
# deploy bans nothing rather than silently mangling the catalog.
@functools.lru_cache(maxsize=1)
def _denylist_prefixes() -> tuple[str, ...]:
    raw = os.getenv('DISCOVERY_DENYLIST_PREFIXES', '')
    if not raw.strip():
        cfg = pathlib.Path(__file__).with_name('discovery_denylist.txt')
        if cfg.exists():
            raw = cfg.read_text()
    seen: dict[str, None] = {}
    for line in raw.replace(',', '\n').splitlines():
        token = line.strip().lower()
        if token and not token.startswith('#'):
            seen[token] = None
    return tuple(seen)


def _is_denylisted(model_id: str) -> bool:
    """True if the model's raw upstream route prefix is on the ban list.

    Matched on the id prefix (the part before the first `/`) exactly, or on a
    shard suffix `<prefix>-...` -- what the upstream actually reports, not the
    derived `provider` column, which does not exist until after this check.
    """
    prefix = model_id.split('/', 1)[0].strip().lower()
    return any(prefix == b or prefix.startswith(b + '-') for b in _denylist_prefixes())


def _display_name(model_id: str) -> str:
    """Turn `deepseek-v4-pro` into `Deepseek V4 Pro` as a starting point.

    Only used for models an admin has not named yet; it is a placeholder, not
    an attempt at correct branding. Words that are one of our own routing or
    reseller identifiers (`_INFRA_TOKENS`) are dropped first, so a raw id like
    `omni/tllm/openrouter_gpt_4_o` cannot regenerate a leaking name like
    "Openrouter Gpt 4 O" on rediscovery.
    """
    bare = model_id.split('/')[-1]
    words = [w for w in re.split(r'[-_.]+', bare) if w and w.lower() not in _INFRA_TOKENS]
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

    Checks top-level keys first (omniroute's shape: `context_length`,
    `max_input_tokens`, ...), then falls back to 9router's shape, which
    nests the real value at `capabilities.contextWindow` instead -- e.g.
    `gemini-api/models/gemini-3.6-flash` reports nothing at the top level
    but `capabilities: {"contextWindow": 1048576, ...}`. Before this
    fallback existed, every such row silently fell through to the 8192
    default despite the upstream actually reporting a real number; three
    gemini-api rows were confirmed already being served that wrong value.
    See migrations/0031_model_modalities.sql for the one-time backfill of
    rows this bug already wrote.
    """
    for key in ('context_window', 'context_length', 'max_context_tokens', 'max_input_tokens'):
        value = raw.get(key)
        if isinstance(value, int) and value > 0:
            return value
    caps = raw.get('capabilities')
    if isinstance(caps, dict):
        value = caps.get('contextWindow')
        if isinstance(value, int) and value > 0:
            return value
    return 8192


def _max_output_tokens(raw: dict[str, Any]) -> int | None:
    """Max output tokens if the upstream reports one, else None.

    The column is nullable (unlike context_window there is no safe
    non-null default to fall back to), so returning None here is an honest
    "unknown", not a bug -- only a value the upstream actually reports is
    ever returned. Same two shapes as `_context_window`: omniroute's
    top-level `max_output_tokens`, 9router's nested
    `capabilities.maxOutput`.
    """
    value = raw.get('max_output_tokens')
    if isinstance(value, int) and value > 0:
        return value
    caps = raw.get('capabilities')
    if isinstance(caps, dict):
        value = caps.get('maxOutput')
        if isinstance(value, int) and value > 0:
            return value
    return None


async def sync_provider(p: Provider) -> dict[str, Any]:
    """Upsert every model one provider reports. Returns a small summary.

    Reads the model list from the provider_catalog cache rather than calling
    the upstream directly — some upstreams (9Router) take ~9.5s to answer
    `GET /v1/models`, and that must never block anything on this path either,
    even though this runs off a background loop rather than a user request.
    """
    if async_session is None:
        return {'provider': p.name, 'error': 'no_db'}

    models = await cached_provider_models(p.name)
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

            # Owner-banned upstream routes (see _denylist_prefixes above) --
            # purged 2026-08-30 and must never be re-landed by a rediscovery.
            if _is_denylisted(model_id):
                continue

            # NOTE on the ON CONFLICT branches below: `model_catalog.provenance
            # <> 'admin-approved'` guards the whole clause, so a curated row is
            # never touched by any of these columns either. On top of
            # that, each column has its own narrower guard so a value someone
            # (an admin, or a previous discovery sweep that already saw a
            # better upstream payload) has since set is never clobbered by a
            # rediscovery that only has a worse or unknown value this time:
            #   * upstream -- only overwritten when the row is NOT currently
            #     sold (availability <> 'available'), or the value is
            #     unchanged. A live, sellable model's upstream is never
            #     silently moved to a different (possibly paid) provider by a
            #     rediscovery -- that would let it keep its old displayed price
            #     while costing more upstream, i.e. sell at a loss (the one
            #     product rule that never reopens). Moving a NON-sold row is
            #     fine: promotion back to 'available' goes through
            #     model_health_policy, which checks margin first (session 11).
            #   * modalities -- only overwritten when the stored value is
            #     still the plain text/text default, OR the newly derived
            #     value is itself non-default (never replace a real
            #     classification with the default).
            #   * context_window -- only overwritten when it is still sitting
            #     at the 8192 fallback AND discovery this time found a real
            #     number (never replace a known value with 8192).
            #   * max_output_tokens -- only filled in when it is still NULL
            #     (never replace a known value with a different one from a
            #     later, possibly less complete, upstream response).
            result = await session.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO model_catalog
                        (id, provider_model_id, provider, display_name, context_window,
                         max_output_tokens, availability, provenance, upstream, modalities,
                         last_verified_at)
                    VALUES
                        (:id, :pmid, :prov, :name, :ctx,
                         :max_out, 'maintenance', 'provider', :upstream, :modalities,
                         now())
                    ON CONFLICT (id) DO UPDATE SET
                        upstream = CASE
                            WHEN model_catalog.availability <> 'available'
                              OR model_catalog.upstream = EXCLUDED.upstream
                            THEN EXCLUDED.upstream
                            ELSE model_catalog.upstream
                        END,
                        last_verified_at = now(),
                        modalities = CASE
                            WHEN model_catalog.modalities = '{"input": ["text"], "output": ["text"]}'::jsonb
                              OR EXCLUDED.modalities <> '{"input": ["text"], "output": ["text"]}'::jsonb
                            THEN EXCLUDED.modalities
                            ELSE model_catalog.modalities
                        END,
                        context_window = CASE
                            WHEN model_catalog.context_window = 8192 AND EXCLUDED.context_window <> 8192
                            THEN EXCLUDED.context_window
                            ELSE model_catalog.context_window
                        END,
                        max_output_tokens = CASE
                            WHEN model_catalog.max_output_tokens IS NULL AND EXCLUDED.max_output_tokens IS NOT NULL
                            THEN EXCLUDED.max_output_tokens
                            ELSE model_catalog.max_output_tokens
                        END
                      WHERE model_catalog.provenance <> 'admin-approved'
                    """
                ),
                {
                    'id': model_id,
                    'pmid': model_id,
                    'prov': _guess_provider(model_id),
                    'name': _display_name(model_id),
                    'ctx': _context_window(raw),
                    'max_out': _max_output_tokens(raw),
                    'upstream': p.name,
                    'modalities': json.dumps(derive_modalities(model_id, raw)),
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
