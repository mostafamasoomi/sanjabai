"""Probe gate for the "honest labelling" product rule (L5).

«مدل فقط بعد از پروب زنده موفق به کاربر ارائه می‌شود» -- a model may be
offered to users only after a successful live probe.

Why this does NOT read model_catalog.last_verified_at: that column is
`NOT NULL DEFAULT now()` (migrations/0001), so a model that model_discovery.py
inserted today and that has never actually been probed already carries
today's timestamp -- it looks fresh while having never been tested. Live
query during the audit that produced this module confirmed all 1155
`maintenance` rows have a `last_verified_at` as recent as the day they were
checked, none of it from an actual probe. That column cannot be used as a
gate; it answers "when was this row last touched", not "was this ever
confirmed working".

The truthful source is `model_health_state.last_ok_at`
(migrations/0016_model_health.sql): NULL until model_health.py's rollup
loop (fed by providers.probe_model, the same probe admin_pricing.py's
POST /admin/models/{id}/test runs on demand) records at least one
successful probe for that model_id. A row that has never been probed has
no model_health_state row at all; a row that has been probed but only ever
failed has a row with `last_ok_at IS NULL`. Both count as "not yet honest
to serve".

WIRED into every admin decision point that can put a model ON SALE
(availability -> 'available'):
    admin_catalog.bulk_set_availability    bulk flip to 'available'
    admin_pricing.toggle_model             single-row flip to 'available'
Withdrawing a model (any other target state) is never gated -- see each
call site's own comment.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy

logger = logging.getLogger(__name__)

# Cap on how many offending ids are named in the Persian detail message --
# a refused 1000-row bulk enable must not dump a 1000-line error at the
# admin; "and N more" carries the same information more usably.
_MAX_NAMED_IDS = 5


@dataclass(frozen=True)
class ProbeRefusal:
    """Why a transition to 'available' may not proceed. Persian text for
    the admin, raw ids for audit_log -- same shape as services/margin.py's
    PriceRefusal."""

    detail: str
    audit: dict[str, Any]


async def refuse_if_unprobed(session, model_ids: Sequence[str]) -> ProbeRefusal | None:
    """None when every id in *model_ids* has a confirmed live probe
    (``model_health_state.last_ok_at IS NOT NULL``), else the refusal
    naming every offending id.

    Refuses the WHOLE set on a single offending id -- never a partial
    bulk-enable -- matching admin_catalog.py's existing bulk-availability
    convention ("the admin never has to work out which half of a bulk
    enable actually landed").

    Fails CLOSED: if the health-table read itself errors, this refuses
    rather than allows, mirroring services/margin.py's documented stance
    (a guard that can't prove safety must not default to permissive).
    Never raises -- a guard that throws on the caller is a guard that gets
    wrapped in a bare `except` and neutered.
    """
    # dict.fromkeys, not set(): de-duplicates a bulk payload that repeats an
    # id while preserving the order ids were given in, so the "first 5"
    # named in the refusal message are deterministic across calls.
    ids = list(dict.fromkeys(str(i) for i in model_ids))
    if not ids:
        return None

    try:
        # Health samples are keyed by whatever id the prober used, which is
        # `provider_model_id` for the background sweep and the catalog `id`
        # for the admin's «تست زنده». Those are the same string for 1,199 of
        # the 1,200 catalog rows -- and for the one where they differ, keying
        # on `id` alone would refuse a model that had in fact been probed
        # successfully. Match either, resolved back to the caller's id.
        res = await session.execute(sqlalchemy.text(
            'SELECT c.id AS catalog_id FROM model_catalog c '
            'JOIN model_health_state s '
            '  ON s.model_id = c.id OR s.model_id = c.provider_model_id '
            'WHERE c.id = ANY(:ids) AND s.last_ok_at IS NOT NULL'
        ), {'ids': ids})
        confirmed = {r.catalog_id for r in res.fetchall()}
    except Exception as e:
        logger.error(f'probe gate: model_health_state read failed for {len(ids)} model(s): {e}')
        return ProbeRefusal(
            detail=(
                'بررسی پروب زنده ممکن نشد، پس فعال‌سازی انجام نشد. مدل فقط بعد از '
                'پروب زنده موفق ارائه می‌شود، و تا وقتی این بررسی ممکن نباشد '
                'فعال‌سازی پذیرفته نمی‌شود.'
            ),
            audit={'model_count': len(ids), 'ids': ids[:50],
                   'reason': f'probe gate could not read model_health_state: {type(e).__name__}'},
        )

    # Ids with no model_health_state row at all never make it into
    # `confirmed` either -- a missing row and a row whose last_ok_at is
    # NULL are the same "never confirmed working" case.
    unprobed = [m for m in ids if m not in confirmed]
    if not unprobed:
        return None

    shown = unprobed[:_MAX_NAMED_IDS]
    names = '، '.join(f'«{m}»' for m in shown)
    remainder = len(unprobed) - len(shown)
    if remainder > 0:
        names += f' و {remainder} مدل دیگر'
    return ProbeRefusal(
        detail=(
            f'این مدل‌ها هنوز پروب زنده موفق ندارند و قابل فعال‌سازی نیستند: {names}. '
            'مدل فقط بعد از پروب زنده موفق به کاربر ارائه می‌شود -- ابتدا «تست زنده» '
            'را روی این مدل‌ها اجرا کنید.'
        ),
        audit={'model_count': len(ids), 'unprobed_count': len(unprobed), 'unprobed_ids': unprobed[:50],
               'reason': "no confirmed live probe (model_health_state.last_ok_at IS NULL or no row)"},
    )
