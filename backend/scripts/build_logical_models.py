#!/usr/bin/env python3
"""Cluster model_catalog rows into logical_model / logical_model_candidate.

Phase 6, Part 1. This script is an admin-run tool, not something the app
calls. It reads every model_catalog row, computes a canonical "logical key"
per the normalization rule below, and proposes a cluster of physical
candidates per logical model.

Dry-run by default: prints the cluster plan and every safety warning, writes
nothing. Pass --apply to actually upsert logical_model / logical_model_candidate.

Nothing this script writes is ever read by the live app in Part 1:
logical_model.availability is always forced to 'maintenance', and the two
tables are only consulted once LOGICAL_ROUTING_ENABLED=true is wired up in a
later part.

Idempotency: rerunning with unchanged catalog data produces zero net change.
A candidate row is "decided" the moment its state leaves 'proposed' (whether
the script itself approved a singleton cluster, or an admin approved/rejected
one by hand) or its added_by is changed to 'admin' -- either way, this script
never touches that row's priority/cost estimate again. logical_model rows
have no such decision flag, so their computed fields (display_name,
context_window, prices) simply refresh to the latest cluster facts on every
run; operational fields an admin owns (availability, routing_policy,
pinned_candidate_id, vendor, description) are never written by this script
after initial creation.

Usage:
    python build_logical_models.py --dry-run
    python build_logical_models.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sanjabai:sanjabai@sanjabai_pg:5432/sanjabai")

# Known internal gateway / sub-route aliases, curated by hand. Kept even
# though the live query below (almost) always finds them too, so a route
# that's temporarily absent from model_catalog (e.g. '9router', retired at
# the time this was written) still gets stripped if it reappears.
CURATED_ROUTE_TOKENS = {
    "omni", "gemini-api", "freellmapi", "freellmapi-s2", "freellmapi-s3",
    "agy", "antigravity", "kc", "gc", "cc", "cx", "kr", "aug", "ddgw",
    "cf", "cloudflare-ai", "9router", "bynara", "bynaraa2", "no-think",
    "opencode-go", "ag", "tllm", "horde",
}
# Google's API echoes 'models' as a path segment (models/gemini-2.5-pro).
# Not a route in our infra, but the same kind of noise -- always stripped.
LITERAL_EXTRA_TOKENS = {"models"}

# Deployment-tier tags to strip -- NOT identity. Everything else (thinking,
# reasoning-effort tiers, quantization, MoE config, -it/-instruct/-distill,
# -preview/-exp, date suffixes, product-name tiers like -mini/-flash) stays.
SUFFIX_ALLOWLIST = (":free", "-free", ":online")

FREE_UPSTREAMS = {"ninerouter", "omniroute", "litellm"}
HEALTH_PRIORITY = {"healthy": 10, "unknown": 50, "degraded": 80, "down": 100}
DEFAULT_PRIORITY = 50  # no model_health_state row at all

CATALOG_COLUMNS = """
    id, provider, display_name, context_window, max_output_tokens,
    currency, input_per_million, output_per_million, cached_input_per_million,
    usd_input_per_million, usd_output_per_million, upstream, provenance
"""


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def build_route_tokens(catalog_ids: list[str]) -> set[str]:
    """Union of the curated list, the dynamic discovery, and 'models'.

    The spec's SELECT DISTINCT split_part(id,'/',1) only reaches the first
    path segment. That misses real cases in this catalog: e.g.
    'openrouter/google/gemma-4-26b-a4b-it:free' needs BOTH 'openrouter' (a
    first segment elsewhere) AND 'google' (never a first segment anywhere --
    it only ever shows up as OpenRouter's own second, vendor-namespace
    segment) stripped to land on the same key as
    'freellmapi/gemma-4-26b-a4b-it' -> 'gemma-4-26b-a4b-it'. Without that
    merge the spec's own worked example (that cluster showing 2 distinct
    prices) cannot happen -- the two rows would sit in different clusters
    and never be compared.

    So this discovers tokens the way the spec's single-level query would if
    applied recursively at every stripping depth, across the whole catalog:
    a token is "known" if it is EVER a non-final '/'-separated segment of
    some catalog id (first segment, or any segment stripping could reach by
    that point). Concretely: every segment except the last, from every id.
    Verified against the live 1134-row catalog that no such token is also
    the complete identity of some other bare (single-segment) id, so this
    cannot eat a real model name.
    """
    discovered: set[str] = set()
    for model_id in catalog_ids:
        segments = model_id.lower().split("/")
        discovered.update(segments[:-1])
    return discovered | CURATED_ROUTE_TOKENS | LITERAL_EXTRA_TOKENS


def normalize(model_id: str, route_tokens: set[str]) -> str:
    """Canonical logical key for a physical model_catalog.id.

    1. lowercase
    2. strip LEADING '/'-separated segments that are known route tokens,
       never emptying the tail
    3. collapse '.', '_' and any leftover '/' into '-'; squeeze repeats; trim
    4. strip exactly one suffix from SUFFIX_ALLOWLIST (checked against the
       literal, still-colon-bearing string -- ':free' only matches before
       step 3 would have nowhere to hide a colon, since colons are never
       touched by step 3)
    """
    s = model_id.lower()
    segments = s.split("/")
    i = 0
    while i < len(segments) - 1 and segments[i] in route_tokens:
        i += 1
    tail = "/".join(segments[i:])

    # Step 4 needs the suffix check to see ':free' / ':online' before the
    # colon would ever be touched -- it never is, so order doesn't actually
    # matter here, but the suffix check happens after separator collapsing
    # so a suffix hidden behind a '.' or '_' (e.g. 'model_free') still needs
    # its own dash form ('-free') to match, which SUFFIX_ALLOWLIST already
    # includes.
    tail = re.sub(r"[._/]", "-", tail)
    tail = re.sub(r"-{2,}", "-", tail).strip("-")

    changed = True
    while changed:
        changed = False
        for suf in SUFFIX_ALLOWLIST:
            if tail.endswith(suf) and len(tail) > len(suf):
                tail = tail[: -len(suf)]
                tail = tail.rstrip("-")
                changed = True

    return tail or s  # never return an empty key


# --------------------------------------------------------------------------
# Cluster-level computation
# --------------------------------------------------------------------------

def pick_display_name(members: list[dict]) -> str:
    approved = [m for m in members if m["provenance"] == "admin-approved" and m["display_name"]]
    pool = approved if approved else members

    def sort_key(m):
        name = m["display_name"] or ""
        has_space = 1 if " " in name else 0
        return (-has_space, -len(name.split()), -len(name), m["id"])

    best = sorted(pool, key=sort_key)[0]
    return best["display_name"] or best["id"]


def pick_context_window(members: list[dict]) -> int:
    vals = [m["context_window"] for m in members if m["context_window"] and m["context_window"] != 8192]
    return max(vals) if vals else 8192


def pick_max_output_tokens(members: list[dict]) -> int | None:
    vals = [m["max_output_tokens"] for m in members if m["max_output_tokens"]]
    return max(vals) if vals else None


def pick_mode(values: list) -> Any:
    """Most common non-null value; ties broken by the smallest value.

    Most clusters have exactly one distinct value, per spec, in which case
    this just returns it. Clusters with more than one distinct value also
    trip the price/context warning below and stay 'proposed', so this pick
    is never used to silently paper over a real inconsistency -- it just
    gives the row *some* deterministic value to display.
    """
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    counts = Counter(vals)
    top = max(counts.values())
    return min(v for v, c in counts.items() if c == top)


def price_warning(members: list[dict]) -> tuple[bool, set]:
    vals = {m["usd_input_per_million"] for m in members if m["usd_input_per_million"] is not None}
    return len(vals) > 1, vals


def context_warning(members: list[dict]) -> tuple[bool, set]:
    vals = {m["context_window"] for m in members if m["context_window"] and m["context_window"] != 8192}
    return len(vals) > 1, vals


def size_warning(members: list[dict]) -> bool:
    return len(members) > 20


def est_cost(member: dict) -> tuple[float | None, float | None]:
    upstream = (member["upstream"] or "").lower()
    if upstream in FREE_UPSTREAMS:
        return 0.0, 0.0
    return None, None


def priority_for(catalog_id: str, health_map: dict[str, str]) -> int:
    status = health_map.get(catalog_id)
    if status is None:
        return DEFAULT_PRIORITY
    return HEALTH_PRIORITY.get(status, DEFAULT_PRIORITY)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

async def load_data(conn: asyncpg.Connection) -> tuple[list[dict], dict[str, str]]:
    catalog_rows = [dict(r) for r in await conn.fetch(f"SELECT {CATALOG_COLUMNS} FROM model_catalog ORDER BY id")]
    health_rows = await conn.fetch("SELECT model_id, status FROM model_health_state")
    health_map = {r["model_id"]: r["status"] for r in health_rows}
    return catalog_rows, health_map


def build_clusters(catalog_rows: list[dict], route_tokens: set[str]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for row in catalog_rows:
        key = normalize(row["id"], route_tokens)
        clusters[key].append(row)
    return clusters


def plan_logical_model(key: str, members: list[dict], health_map: dict[str, str]) -> dict:
    is_singleton = len(members) == 1
    price_warn, price_vals = price_warning(members)
    ctx_warn, ctx_vals = context_warning(members)
    oversized = size_warning(members)
    warnings = []
    if price_warn:
        warnings.append(("price_inconsistency", sorted(price_vals)))
    if ctx_warn:
        warnings.append(("context_inconsistency", sorted(ctx_vals)))
    if oversized:
        warnings.append(("oversized_cluster", len(members)))

    logical = {
        "key": key,
        "display_name": pick_display_name(members),
        "context_window": pick_context_window(members),
        "max_output_tokens": pick_max_output_tokens(members),
        "currency": "IRT",
        "input_per_million": pick_mode([m["input_per_million"] for m in members]) or 0,
        "output_per_million": pick_mode([m["output_per_million"] for m in members]) or 0,
        "cached_input_per_million": pick_mode([m["cached_input_per_million"] for m in members]),
        "usd_input_per_million": pick_mode([m["usd_input_per_million"] for m in members]),
        "usd_output_per_million": pick_mode([m["usd_output_per_million"] for m in members]),
        "availability": "maintenance",
    }

    candidates = []
    for m in members:
        cost_in, cost_out = est_cost(m)
        candidates.append({
            "catalog_id": m["id"],
            "priority": priority_for(m["id"], health_map),
            "state": "approved" if is_singleton else "proposed",
            "est_cost_usd_input": cost_in,
            "est_cost_usd_output": cost_out,
        })

    return {"logical": logical, "candidates": candidates, "warnings": warnings, "size": len(members)}


async def apply_plan(conn: asyncpg.Connection, plans: list[dict]) -> None:
    async with conn.transaction():
        for plan in plans:
            lm = plan["logical"]
            await conn.execute(
                """
                INSERT INTO logical_model
                    (key, display_name, context_window, max_output_tokens, currency,
                     input_per_million, output_per_million, cached_input_per_million,
                     usd_input_per_million, usd_output_per_million, availability)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'maintenance')
                ON CONFLICT (key) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    context_window = EXCLUDED.context_window,
                    max_output_tokens = EXCLUDED.max_output_tokens,
                    input_per_million = EXCLUDED.input_per_million,
                    output_per_million = EXCLUDED.output_per_million,
                    cached_input_per_million = EXCLUDED.cached_input_per_million,
                    usd_input_per_million = EXCLUDED.usd_input_per_million,
                    usd_output_per_million = EXCLUDED.usd_output_per_million,
                    updated_at = now()
                """,
                lm["key"], lm["display_name"], lm["context_window"], lm["max_output_tokens"],
                lm["currency"], lm["input_per_million"], lm["output_per_million"],
                lm["cached_input_per_million"], lm["usd_input_per_million"], lm["usd_output_per_million"],
            )
            for c in plan["candidates"]:
                await conn.execute(
                    """
                    INSERT INTO logical_model_candidate
                        (logical_key, catalog_id, priority, enabled, state,
                         est_cost_usd_input, est_cost_usd_output, added_by)
                    VALUES ($1,$2,$3,true,$4,$5,$6,'clusterer')
                    ON CONFLICT (logical_key, catalog_id) DO UPDATE SET
                        priority = EXCLUDED.priority,
                        est_cost_usd_input = EXCLUDED.est_cost_usd_input,
                        est_cost_usd_output = EXCLUDED.est_cost_usd_output,
                        updated_at = now()
                    WHERE logical_model_candidate.added_by <> 'admin'
                      AND logical_model_candidate.state = 'proposed'
                    """,
                    lm["key"], c["catalog_id"], c["priority"], c["state"],
                    c["est_cost_usd_input"], c["est_cost_usd_output"],
                )


def print_report(plans: list[dict]) -> None:
    total_members = sum(p["size"] for p in plans)
    singleton = sum(1 for p in plans if p["size"] == 1)
    multi = len(plans) - singleton
    warned = [p for p in plans if p["warnings"]]

    print(f"[build_logical_models] {total_members} catalog rows -> {len(plans)} clusters "
          f"({singleton} singleton, {multi} multi-member)")
    print(f"[build_logical_models] {len(warned)} cluster(s) tripped a safety warning "
          f"(forced to stay proposed):")
    for p in sorted(warned, key=lambda p: p["logical"]["key"]):
        key = p["logical"]["key"]
        for kind, detail in p["warnings"]:
            print(f"    WARN  {key:50s} {kind:22s} {detail}")

    biggest = sorted(plans, key=lambda p: -p["size"])[:10]
    print("[build_logical_models] 10 largest clusters:")
    for p in biggest:
        print(f"    {p['size']:3d}  {p['logical']['key']}")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write to logical_model / logical_model_candidate. Default is dry run.")
    ap.add_argument("--dry-run", action="store_true", help="Explicit no-op flag (dry run is already the default).")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        print("[build_logical_models] --apply and --dry-run both given; refusing to guess. Aborting.", file=sys.stderr)
        sys.exit(1)

    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(db_url)

    if args.apply:
        exists = await conn.fetchval("SELECT to_regclass('public.logical_model')")
        if exists is None:
            print("[build_logical_models] logical_model does not exist yet -- migration 0025 has not "
                  "been applied. Refusing to --apply. Run a dry run instead.", file=sys.stderr)
            await conn.close()
            sys.exit(1)

    catalog_rows, health_map = await load_data(conn)
    route_tokens = build_route_tokens([row["id"] for row in catalog_rows])
    clusters = build_clusters(catalog_rows, route_tokens)
    plans = [plan_logical_model(key, members, health_map) for key, members in clusters.items()]

    print_report(plans)

    if args.apply:
        print(f"[build_logical_models] APPLY: writing {len(plans)} logical models "
              f"and {sum(p['size'] for p in plans)} candidates")
        await apply_plan(conn, plans)
        print("[build_logical_models] done")
    else:
        print("[build_logical_models] DRY RUN: nothing written. Pass --apply to write.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
