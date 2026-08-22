"""Guardrail: a user's wallet may be credited only by (a) the payment
gateway (payment.py) or (b) an admin (admin_user_ops.py). Nothing else.

The signup gift and referral bonus that used to live in auth.py violated
this rule -- both have been removed (see auth.py). This test makes the rule
durable: it statically scans backend source for every call site that could
*increase* a wallet balance and asserts the set of modules doing so is
exactly the allowed set. A future change that adds a new crediting call site
anywhere else will fail this test until the allowlist below is deliberately
edited -- which is the point: a reviewer has to see it.

Scope is backend/*.py and backend/services/*.py (application code that can
run in production), not backend/tests/*.py or backend/migrations/*.sql.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Modules allowed to increase a wallet balance.
#   - payment.py          : the payment gateway callback (Zarinpal verify -> credit_wallet)
#   - admin_user_ops.py    : admin-only wallet-adjust endpoint (credit_wallet for 'credit' direction)
#   - services/billing.py  : *defines* credit_wallet, and contains its own
#     internal ledger-append (the credit side of the reserve/settle machinery).
#     Nothing outside this file is allowed to append a positive ledger entry
#     directly -- everyone else must go through credit_wallet (or the admin
#     debit helper, which is a different, negative-amount code path).
ALLOWED_CREDIT_MODULES = frozenset({
    "payment.py",
    "admin_user_ops.py",
    "services/billing.py",
})

REMOVED_TXN_TYPES = ("signup_bonus", "referral_bonus")


# ── source loading ──────────────────────────────────────────────────────

def _load_backend_sources() -> dict[str, str]:
    """{relpath: text} for backend/*.py and backend/services/*.py."""
    sources: dict[str, str] = {}
    for path in sorted(BACKEND.glob("*.py")):
        sources[path.name] = path.read_text(encoding="utf-8")
    for path in sorted((BACKEND / "services").glob("*.py")):
        sources[f"services/{path.name}"] = path.read_text(encoding="utf-8")
    return sources


# ── the detector ─────────────────────────────────────────────────────────
#
# This is a coarse regex/heuristic scanner, not a type-checker. It is
# deliberately biased to over-flag: a call site it can't prove is a debit
# gets flagged as a possible credit. A false positive just means a legitimate
# new module has to be added to the allowlist above (a one-line, reviewed
# edit); a false negative would mean a real, silent wallet-credit path slips
# past this guard entirely, which is the exact failure this test exists to
# prevent. Bias accordingly.

_CREDIT_WALLET_CALL = re.compile(r"\bcredit_wallet\s*\(")
_LEDGER_SITE = re.compile(r"append_ledger\s*\(\s*\{|\bLedger\s*\(")
_DEF_LINE = re.compile(r"^\s*(?:async\s+)?def\s+credit_wallet\s*\(")
_CLASS_LEDGER_LINE = re.compile(r"^\s*class\s+Ledger\b")


def _line_at(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start: end if end != -1 else len(text)]


def _line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _matching_window(text: str, open_pos: int, max_len: int = 400) -> str:
    """Bounded slice of text from an opening bracket to its matching close
    (falls back to max_len if unbalanced or too far away)."""
    opener = text[open_pos]
    closer = {"(": ")", "{": "}"}[opener]
    depth = 0
    end = min(len(text), open_pos + max_len)
    for i in range(open_pos, end):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[open_pos:i + 1]
    return text[open_pos:end]


def _credit_wallet_call_lines(text: str) -> list[int]:
    """Line numbers of credit_wallet(...) *calls* (excludes its `def`)."""
    hits = []
    for m in _CREDIT_WALLET_CALL.finditer(text):
        if _DEF_LINE.match(_line_at(text, m.start())):
            continue
        hits.append(_line_no(text, m.start()))
    return hits


def _positive_ledger_insert_lines(text: str) -> list[int]:
    """Line numbers of append_ledger({...}) / Ledger(...) sites whose
    `amount=`/`amount:` value is not manifestly a unary-negative expression.

    A `class Ledger(Base):` definition is not a call site and is excluded.
    A site with no `amount=` found in its window can't be proven negative,
    so (per the over-flag bias above) it is treated as a possible credit.
    """
    hits = []
    for m in _LEDGER_SITE.finditer(text):
        if _CLASS_LEDGER_LINE.match(_line_at(text, m.start())):
            continue
        open_pos = m.end() - 1  # index of the '(' or '{' just matched
        window = _matching_window(text, open_pos)
        amt = re.search(r"amount\s*[=:]\s*(-)?", window)
        if amt is None or amt.group(1) != "-":
            hits.append(_line_no(text, m.start()))
    return hits


def find_wallet_credit_violations(
    sources: dict[str, str], allowed: frozenset[str],
) -> list[str]:
    """Return human-readable violation strings for every wallet-increasing
    call site found outside `allowed` modules."""
    violations: list[str] = []
    for relpath, text in sources.items():
        if relpath in allowed:
            continue
        for line in _credit_wallet_call_lines(text):
            violations.append(f"{relpath}:{line}: disallowed credit_wallet( call")
        for line in _positive_ledger_insert_lines(text):
            violations.append(
                f"{relpath}:{line}: disallowed ledger insert with non-negative amount"
            )
    return violations


# ── the real scan ────────────────────────────────────────────────────────

def test_only_allowed_modules_credit_the_wallet():
    sources = _load_backend_sources()
    violations = find_wallet_credit_violations(sources, ALLOWED_CREDIT_MODULES)
    assert not violations, (
        "Found wallet-crediting call site(s) outside the allowed modules "
        f"{sorted(ALLOWED_CREDIT_MODULES)}. A wallet may be credited only by "
        "the payment gateway or an admin. If this is a deliberate new "
        "credit path, add it to ALLOWED_CREDIT_MODULES in this test as a "
        "reviewed decision:\n" + "\n".join(violations)
    )


def test_auth_py_has_no_credit_wallet_call():
    """auth.py must not call credit_wallet at all -- it is not on the
    allowlist and the two credit paths that lived there (signup gift,
    referral bonus) were deliberately removed."""
    text = (BACKEND / "auth.py").read_text(encoding="utf-8")
    assert not _credit_wallet_call_lines(text)


def test_removed_txn_types_do_not_reappear():
    """The two removed ledger txn_type literals must not resurface anywhere
    in backend/*.py under the old names -- a future change reintroducing the
    signup gift or referral bonus (even accidentally, e.g. by copy-pasting
    old code back) must not do so silently under a name this guard doesn't
    recognize as new."""
    violations = []
    for path in sorted(BACKEND.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for txn_type in REMOVED_TXN_TYPES:
            if txn_type in text:
                violations.append(f"{path.name}: contains removed txn_type '{txn_type}'")
    assert not violations, "\n".join(violations)


# ── guard the guard ──────────────────────────────────────────────────────
#
# This repo has been bitten before by guards that silently do nothing: a
# migration guard that skipped the file it was meant to check, and a claim
# guard that only ever matched inside comments. These canaries run the same
# detector functions above over synthetic source attributed to a disallowed
# module and assert a violation IS raised -- proving the scanner can fail
# loudly, not just pass quietly.

def test_canary_detects_disallowed_credit_wallet_call():
    synthetic_sources = {
        "some_new_feature.py": (
            "from services.billing import SqlBillingRepo, credit_wallet\n"
            "from services.money import Money\n\n"
            "async def sneaky_bonus(session, user_id):\n"
            "    await credit_wallet(\n"
            "        SqlBillingRepo(session), user_id, Money(5000),\n"
            "        reason='free money', txn_type='signup_bonus',\n"
            "    )\n"
        ),
    }
    violations = find_wallet_credit_violations(synthetic_sources, ALLOWED_CREDIT_MODULES)
    assert any("some_new_feature.py" in v and "credit_wallet" in v for v in violations), (
        "Canary failed: the scanner did not flag a credit_wallet( call in a "
        "disallowed synthetic module. The detector is broken."
    )


def test_canary_detects_disallowed_positive_ledger_insert():
    synthetic_sources = {
        "another_new_feature.py": (
            "async def sneaky_direct_ledger(session, user_id, new_balance):\n"
            "    session.add(Ledger(\n"
            "        user_id=user_id, txn_type='credit', amount=5000,\n"
            "        balance_after=new_balance, reason='oops',\n"
            "    ))\n"
        ),
    }
    violations = find_wallet_credit_violations(synthetic_sources, ALLOWED_CREDIT_MODULES)
    assert any("another_new_feature.py" in v for v in violations), (
        "Canary failed: the scanner did not flag a positive-amount Ledger(...) "
        "insert in a disallowed synthetic module. The detector is broken."
    )


def test_canary_allows_negative_ledger_insert_debit():
    """Sanity check on the other side: a debit (negative amount) in a
    disallowed module must NOT be flagged as a credit violation -- otherwise
    this guard would also be wrong in the other direction (crying wolf on
    legitimate debits, e.g. usage charges or hermes renewals)."""
    synthetic_sources = {
        "a_debit_feature.py": (
            "async def charge_usage(session, user_id, new_balance, charged):\n"
            "    session.add(Ledger(\n"
            "        user_id=user_id, txn_type='usage', amount=-charged,\n"
            "        balance_after=new_balance, reason='usage',\n"
            "    ))\n"
        ),
    }
    violations = find_wallet_credit_violations(synthetic_sources, ALLOWED_CREDIT_MODULES)
    assert not violations, f"False positive on a manifest debit: {violations}"


def test_canary_allows_allowed_module_even_with_credit_call():
    """The allowlist mechanism itself must actually suppress allowed
    modules -- otherwise the allowlist would be decorative."""
    synthetic_sources = {
        "payment.py": (
            "async def handle_callback(repo, user_id, amount):\n"
            "    await credit_wallet(repo, user_id, amount, reason='topup')\n"
        ),
    }
    violations = find_wallet_credit_violations(synthetic_sources, ALLOWED_CREDIT_MODULES)
    assert not violations
