"""Regression guard for model_discovery.py's ON CONFLICT upstream branch.

Session 13. Before this fix the discovery upsert did
``ON CONFLICT (id) DO UPDATE SET upstream = EXCLUDED.upstream`` -- it moved a
model's upstream to whatever provider a rediscovery last saw, with no margin
guard. The statement-level ``WHERE provenance <> 'admin-approved'`` protects
curated rows, but an auto-discovered row that is currently ``available`` (being
sold) keeps its availability across the UPDATE. So with a paid upstream
(OpenRouter, phase F3) enabled, a live sellable model could have its upstream
swapped to the paid route while keeping its old displayed price -- selling at a
loss, the one product rule that never reopens (هیچ درخواستی نباید ضررده باشد).
Session 11 closed the twin hole in model_health_policy.py; this closed this one.

The fix gates the overwrite: upstream is only replaced when the row is NOT
currently sold (``availability <> 'available'``) or the value is unchanged.
Moving a non-sold row still works -- promotion back to ``available`` re-checks
margin in model_health_policy.

Proven live before deploy, against production, each in a rolled-back txn:
    OLD  cc/claude-sonnet-5 (available): ninerouter -> openrouter  (loss risk)
    NEW  cc/claude-sonnet-5 (available): ninerouter -> ninerouter  (kept, safe)
    NEW  auto/best-chaos    (maintenance): omniroute -> openrouter (still moves)

The suite mocks async_session, so ON CONFLICT is never executed here; this is a
source-level guard, so a revert to the naked overwrite fails CI. The behavioral
proof lives in the session log, not in an assertion this file can run.
"""
from __future__ import annotations

import pathlib
import re

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'model_discovery.py').read_text()


def _on_conflict_upstream_block() -> str:
    """The DO UPDATE SET body up to the provenance guard, as one chunk."""
    m = re.search(
        r'ON CONFLICT \(id\) DO UPDATE SET(.+?)WHERE model_catalog\.provenance',
        _SRC, re.S)
    assert m, 'ON CONFLICT upstream upsert not found -- did the statement move?'
    return m.group(1)


def test_upstream_overwrite_is_gated_on_availability():
    block = _on_conflict_upstream_block()
    assert re.search(r'upstream\s*=\s*CASE', block), \
        'upstream is not a CASE expression -- the session-13 loss guard is gone'
    assert "availability <> 'available'" in block, \
        'upstream overwrite is not gated on availability -- a live sellable ' \
        'model can be silently swapped to a paid upstream and sold at a loss'


def test_naked_unconditional_upstream_overwrite_never_returns():
    block = _on_conflict_upstream_block()
    assert not re.search(r'upstream\s*=\s*EXCLUDED\.upstream\s*,', block), \
        'naked `upstream = EXCLUDED.upstream,` is back -- session-13 guard reverted'
