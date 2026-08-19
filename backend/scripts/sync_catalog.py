#!/usr/bin/env python3
"""Sync model_catalog prices from the OpenRouter public models API.

Only pricing fields are touched: input_per_million, output_per_million,
usd_input_per_million, usd_output_per_million, updated_at. provider,
upstream, availability, display_name and everything else are left alone.

Rows with provenance = 'admin-approved' are never written to, unless
--include-admin-approved is explicitly passed.

The USD->IRT rate used for conversion is (base rate) + (--usd-irt-markup),
so margin is applied uniformly as a markup on the exchange rate itself,
not on individual model prices. Both the base rate and the markup are
recorded in the JSON report so the effective rate is always auditable.

Default is DRY RUN: nothing is written unless --apply is passed.
A JSON report of every decision is written to the path given by --report.

Usage:
    python sync_catalog.py --report /root/sync_report.json
    python sync_catalog.py --report /root/sync_report.json --usd-irt 188600
    python sync_catalog.py --report /root/sync_report.json --usd-irt 188600 --usd-irt-markup 2000
    python sync_catalog.py --report /root/sync_report.json --usd-irt 188600 --include-admin-approved
    python sync_catalog.py --report /root/sync_report.json --usd-irt 188600 --apply
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

import asyncpg
import httpx

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sanjabai:sanjabai@sanjabai_pg:5432/sanjabai")
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Router-wrapper artifacts that OpenRouter never encodes in a model id.
# Safe to strip unconditionally because they describe *how* our router calls
# the model (reasoning effort), not a different priced SKU on OpenRouter.
EFFORT_SUFFIXES = ("medium", "high", "low", "reasoning")

# Suffixes that CAN map to a real, separately-priced OpenRouter SKU
# (":free" / ":thinking"). These are tried in colon form first so we never
# silently substitute the paid price for a model tagged as free (or vice
# versa). Only if that fails do we fall back to the base SKU, and that
# fallback is flagged low-confidence in the report.
MODIFIERS = ("free", "thinking")


def normalize(s: str) -> str:
    s = s.strip().lower().lstrip("~")
    s = re.sub(r"[_.\s]", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def strip_effort_suffix(slug: str) -> str:
    for suf in EFFORT_SUFFIXES:
        if slug.endswith("-" + suf):
            return slug[: -(len(suf) + 1)]
    return slug


def slug_variants(slug: str):
    """Yield (slug, modifier) lookup attempts, strictest/most-faithful first.

    modifier is None for a plain SKU lookup, or 'free'/'thinking' when we
    are deliberately trying to hit OpenRouter's colon-suffixed variant.
    """
    seen = set()

    def emit(s, mod, tag):
        key = (s, mod)
        if key not in seen:
            seen.add(key)
            return (s, mod, tag)
        return None

    r = emit(slug, None, "exact")
    if r:
        yield r

    for mod in MODIFIERS:
        if slug.endswith("-" + mod):
            base = slug[: -(len(mod) + 1)]
            r = emit(base, mod, "colon-form")
            if r:
                yield r

    stripped = strip_effort_suffix(slug)
    if stripped != slug:
        r = emit(stripped, None, "effort-stripped")
        if r:
            yield r
        for mod in MODIFIERS:
            if stripped.endswith("-" + mod):
                base = stripped[: -(len(mod) + 1)]
                r = emit(base, mod, "effort-and-colon-form")
                if r:
                    yield r

    # Last resort: drop a free/thinking suffix outright and match the base
    # SKU's normal price. Flagged low-confidence by the caller.
    for s in (slug, stripped):
        for mod in MODIFIERS:
            if s.endswith("-" + mod):
                base = s[: -(len(mod) + 1)]
                r = emit(base, None, "modifier-fallback-to-base")
                if r:
                    yield r


CONFIDENCE = {
    "exact": "high",
    "colon-form": "high",
    "effort-stripped": "medium",
    "effort-and-colon-form": "medium",
    "modifier-fallback-to-base": "low",
}

NOTES = {
    "exact": "direct normalized match",
    "colon-form": "matched OpenRouter's :{mod} priced variant",
    "effort-stripped": "stripped router-only effort suffix ({mod_src}), then matched",
    "effort-and-colon-form": "stripped effort suffix and matched :{mod} priced variant",
    "modifier-fallback-to-base": "row name implies '{mod_src}' but no distinctly-priced "
    "OpenRouter variant exists; matched to the base SKU's normal price -- verify manually",
}


async def fetch_openrouter_index(client: httpx.AsyncClient):
    """Build lookup indexes from the OpenRouter public catalog.

    or_by_full:  (vendor, slug, modifier) -> (raw_id, usd_in, usd_out)
    or_by_slug:  (slug, modifier)         -> [(vendor, raw_id, usd_in, usd_out), ...]
    """
    resp = await client.get(OPENROUTER_MODELS_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    or_by_full, or_by_slug = {}, {}
    real_vendors = set()
    skipped = 0
    for m in data:
        raw_id = m.get("id", "")
        if not raw_id or raw_id.startswith("~"):
            continue  # '~vendor/x-latest' aliases just duplicate another entry
        if "/" not in raw_id.split(":", 1)[0]:
            continue
        path, _, mod = raw_id.partition(":")
        mod = mod or None
        vendor, _, slug = path.partition("/")
        pricing = m.get("pricing", {}) or {}
        try:
            usd_in = float(pricing.get("prompt")) * 1_000_000
            usd_out = float(pricing.get("completion")) * 1_000_000
        except (TypeError, ValueError):
            skipped += 1
            continue
        if usd_in < 0 or usd_out < 0:
            # OpenRouter uses "-1" as a sentinel for variable/pass-through
            # pricing on meta-router models (e.g. openrouter/auto). Not a
            # real price -- must not be used.
            skipped += 1
            continue
        norm_slug = normalize(slug)
        key_full = (vendor, norm_slug, mod)
        or_by_full[key_full] = (raw_id, usd_in, usd_out)
        or_by_slug.setdefault((norm_slug, mod), []).append((vendor, raw_id, usd_in, usd_out))
        real_vendors.add(vendor)

    return or_by_full, or_by_slug, real_vendors, len(data), skipped


def candidate_strings(row):
    """Yield normalized (vendor_or_None, slug) tuples, most specific first."""
    seen = set()
    for field in (row["id"], row["provider_model_id"]):
        if not field:
            continue
        segs = [s for s in field.split("/") if s]
        for i in range(len(segs)):
            slice_ = segs[i:]
            vendor = normalize(slice_[0]) if len(slice_) > 1 else None
            slug = normalize(slice_[-1])
            key = (vendor, slug)
            if key not in seen:
                seen.add(key)
                yield key
    provider = normalize(row["provider"] or "")
    if provider:
        last_seg = normalize((row["id"] or row["provider_model_id"] or "").split("/")[-1])
        key = (provider, last_seg)
        if key not in seen:
            seen.add(key)
            yield key


def find_match(row, or_by_full, or_by_slug, real_vendors):
    for vendor, slug in candidate_strings(row):
        if not slug:
            continue
        # A bare slug (no path vendor) sometimes still carries the vendor
        # name baked into the model name itself, e.g. catalog id
        # "tencent-hy3-free" vs OpenRouter "tencent/hy3". Recognize that so
        # we don't miss real matches just because our router flattened the
        # id to a single segment.
        guesses = [(vendor, slug, False)]
        if vendor is None:
            for v in sorted(real_vendors, key=len, reverse=True):
                if slug.startswith(v + "-") and len(slug) > len(v) + 1:
                    guesses.append((v, slug[len(v) + 1:], True))

        for v_guess, eff_slug, embedded in guesses:
            for variant_slug, mod, tag in slug_variants(eff_slug):
                if v_guess and (v_guess, variant_slug, mod) in or_by_full:
                    raw_id, usd_in, usd_out = or_by_full[(v_guess, variant_slug, mod)]
                    return _match_result(raw_id, usd_in, usd_out, tag, mod, embedded)
                cands = or_by_slug.get((variant_slug, mod))
                if cands and len(cands) == 1:
                    _, raw_id, usd_in, usd_out = cands[0]
                    return _match_result(raw_id, usd_in, usd_out, tag, mod, embedded)
    return None


def _match_result(raw_id, usd_in, usd_out, tag, mod, embedded=False):
    note = NOTES[tag].format(mod=mod, mod_src=mod)
    confidence = CONFIDENCE[tag]
    method = tag
    if embedded:
        note += "; vendor name was embedded in the catalog id and split off to match"
        method = tag + "+vendor-embedded"
    return {
        "matched_openrouter_id": raw_id,
        "usd_input_per_million": round(usd_in, 6),
        "usd_output_per_million": round(usd_out, 6),
        "match_method": method,
        "confidence": confidence,
        "note": note,
    }


async def resolve_usd_irt_rate(conn, cli_rate):
    row = await conn.fetchrow(
        "SELECT rate FROM exchange_rate_overrides WHERE from_currency = 'USD' "
        "AND to_currency = 'IRT' AND active = TRUE ORDER BY id DESC LIMIT 1"
    )
    if row is not None:
        return float(row["rate"]), "exchange_rate_overrides table"
    if cli_rate is not None:
        return float(cli_rate), "--usd-irt CLI flag"
    print(
        "[error] no active USD->IRT rate in exchange_rate_overrides, and no "
        "--usd-irt flag was given. Refusing to guess a rate. Aborting.",
        file=sys.stderr,
    )
    sys.exit(1)


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually write changes. Default is dry run.")
    ap.add_argument("--usd-irt", type=float, default=None, help="Fallback USD->IRT rate if no active override exists.")
    ap.add_argument(
        "--usd-irt-markup",
        type=float,
        default=2000,
        help="Flat Toman amount added to the base USD->IRT rate before conversion, "
        "so margin is uniform across models. Effective rate = base rate + markup. "
        "Default 2000.",
    )
    ap.add_argument(
        "--include-admin-approved",
        action="store_true",
        help="Price provenance='admin-approved' rows too, instead of skipping them. "
        "Default OFF, so unattended runs never touch human-approved rows.",
    )
    ap.add_argument("--report", required=True, help="Path to write the JSON report to.")
    args = ap.parse_args()

    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(db_url)

    usd_irt_base_rate, rate_source = await resolve_usd_irt_rate(conn, args.usd_irt)
    usd_irt_markup = args.usd_irt_markup
    usd_irt_rate = usd_irt_base_rate + usd_irt_markup
    print(
        f"[sync] USD->IRT base rate = {usd_irt_base_rate} (source: {rate_source}), "
        f"markup = {usd_irt_markup}, effective rate = {usd_irt_rate}"
    )
    if args.include_admin_approved:
        print("[sync] --include-admin-approved passed: admin-approved rows WILL be priced")

    async with httpx.AsyncClient() as client:
        or_by_full, or_by_slug, real_vendors, or_total, or_skipped = await fetch_openrouter_index(client)
    print(f"[sync] OpenRouter: {or_total} models fetched, {or_skipped} skipped (no usable pricing)")

    rows = await conn.fetch(
        "SELECT id, provider, provider_model_id, upstream, availability, provenance, "
        "usd_input_per_million, usd_output_per_million FROM model_catalog ORDER BY id"
    )
    print(f"[sync] {len(rows)} catalog rows loaded")

    report_entries = []
    counts = {"would-update": 0, "no-change": 0, "would-skip-admin-approved": 0, "no-price-source": 0}

    to_write = []  # (id, irt_in, irt_out, usd_in, usd_out) only when --apply and would-update

    for row in rows:
        match = find_match(row, or_by_full, or_by_slug, real_vendors)
        entry = {
            "id": row["id"],
            "provider": row["provider"],
            "upstream": row["upstream"],
            "provenance": row["provenance"],
            "matched_openrouter_id": None,
            "usd_input_per_million": None,
            "usd_output_per_million": None,
            "irt_input_per_million": None,
            "irt_output_per_million": None,
            "action": None,
            "match_method": None,
            "confidence": None,
            "note": None,
        }

        if row["provenance"] == "admin-approved" and not args.include_admin_approved:
            entry["action"] = "would-skip-admin-approved"
            if match:
                entry["matched_openrouter_id"] = match["matched_openrouter_id"]
                entry["note"] = "admin-approved row -- never written to, shown for reference only"
            counts["would-skip-admin-approved"] += 1
            report_entries.append(entry)
            continue

        if not match:
            entry["action"] = "no-price-source"
            entry["note"] = "no OpenRouter model matched this id after fuzzy normalization"
            counts["no-price-source"] += 1
            report_entries.append(entry)
            continue

        usd_in = match["usd_input_per_million"]
        usd_out = match["usd_output_per_million"]
        irt_in = round(usd_in * usd_irt_rate)
        irt_out = round(usd_out * usd_irt_rate)

        entry.update(
            matched_openrouter_id=match["matched_openrouter_id"],
            usd_input_per_million=usd_in,
            usd_output_per_million=usd_out,
            irt_input_per_million=irt_in,
            irt_output_per_million=irt_out,
            match_method=match["match_method"],
            confidence=match["confidence"],
            note=match["note"],
        )

        current_usd_in = float(row["usd_input_per_million"] or 0)
        current_usd_out = float(row["usd_output_per_million"] or 0)
        if abs(current_usd_in - usd_in) < 1e-9 and abs(current_usd_out - usd_out) < 1e-9:
            entry["action"] = "no-change"
            counts["no-change"] += 1
        else:
            entry["action"] = "would-update"
            counts["would-update"] += 1
            to_write.append((row["id"], irt_in, irt_out, usd_in, usd_out))

        report_entries.append(entry)

    # The DB-level guard against clobbering admin-approved rows stays in
    # place by default even if to_write somehow contained one. It is only
    # relaxed when --include-admin-approved was explicitly passed, which is
    # the single, opt-in way to price those rows.
    update_sql = "UPDATE model_catalog SET input_per_million = $2, output_per_million = $3, " \
        "usd_input_per_million = $4, usd_output_per_million = $5, updated_at = now() WHERE id = $1"
    if not args.include_admin_approved:
        update_sql += " AND provenance != 'admin-approved'"

    if args.apply:
        print(f"[sync] APPLY MODE: writing {len(to_write)} price updates")
        async with conn.transaction():
            for model_id, irt_in, irt_out, usd_in, usd_out in to_write:
                await conn.execute(update_sql, model_id, irt_in, irt_out, usd_in, usd_out)
    else:
        print(f"[sync] DRY RUN: would write {len(to_write)} price updates (pass --apply to write)")

    await conn.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "applied": args.apply,
        "include_admin_approved": args.include_admin_approved,
        "usd_irt_base_rate": usd_irt_base_rate,
        "usd_irt_base_rate_source": rate_source,
        "usd_irt_markup": usd_irt_markup,
        "usd_irt_effective_rate": usd_irt_rate,
        # Kept for backward compatibility with prior report consumers --
        # equal to usd_irt_effective_rate, the rate actually used for
        # every IRT conversion above.
        "usd_irt_rate": usd_irt_rate,
        "usd_irt_rate_source": rate_source,
        "openrouter_models_fetched": or_total,
        "catalog_rows": len(rows),
        "counts": counts,
        "models": report_entries,
    }
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[sync] report written to {args.report}")
    print(f"[sync] summary: {counts}")


if __name__ == "__main__":
    asyncio.run(main())
