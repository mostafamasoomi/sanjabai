"""Guardrail: frontend copy must not contain unregistered/unverified claims.

Any user-facing marketing number (model counts, uptime %, gift/credit amounts)
must come from the claim registry (frontend/lib/claims.ts backed by the DB
`claims` table) — never hardcoded in page copy. See docs/claims-policy.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Directories that hold user-facing source (skip build output / deps).
SCAN_DIRS = ["app", "components", "lib"]
# claims.ts is the registry itself; it is allowed to define copy.
ALLOWLIST = {"lib/claims.ts"}

FORBIDDEN = [
    (re.compile(r"۵۰\s*\+|(?<!\d)50\s*\+"), "unverified model-count claim (50+)"),
    # Anchored to a percent sign — a bare "99[.,]9|۹۹[.,]۹" also matches any
    # coincidental occurrence of that digit sequence in unrelated numeric
    # data, e.g. SVG path coordinates in components/ui/Icon.tsx.
    (re.compile(r"99[.,]9\s*%|۹۹[.,]۹\s*(%|٪)"), "unverified uptime percentage (99.9%)"),
    (re.compile(r"uptime", re.IGNORECASE), "uptime claim"),
    (
        re.compile(r"(۱۰[،,]?۰۰۰|10[,]?000)\s*(تومان|toman)", re.IGNORECASE),
        "unverified gift/credit amount (10,000 Toman)",
    ),
]


def _iter_source_files():
    for d in SCAN_DIRS:
        base = FRONTEND / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            rel = path.relative_to(FRONTEND).as_posix()
            if rel in ALLOWLIST:
                continue
            yield rel, path


@pytest.mark.skipif(not FRONTEND.exists(), reason="frontend not present")
def test_no_unregistered_claims_in_frontend_copy():
    violations: list[str] = []
    for rel, path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in FORBIDDEN:
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                violations.append(f"{rel}:{line}: {label} -> '{m.group(0)}'")
    assert not violations, "Unregistered claims found in frontend copy:\n" + "\n".join(violations)
