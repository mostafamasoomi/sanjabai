"""Guardrail: a user's wallet may be credited only by (a) the payment
gateway (payment.py), (b) an admin (admin_user_ops.py), or (c) the referral
reward settlement (services/referral.py). Nothing else.

The signup gift that used to live in auth.py violated this rule and was
removed (see auth.py) and stays removed permanently -- REMOVED_TXN_TYPES
below still bans its txn_type literal, 'signup_bonus', everywhere.

The referral bonus is DIFFERENT from the old removed one, and this file's
contract changed for it -- owner decision, recorded 2026-08-28, in
services/referral.py's module docstring: a referral reward is real, but it
is paid on the INVITEE's first successful payment (payment_endpoints.py ->
services.referral.settle_on_first_payment(), never at signup), and it is
paid from exactly one sanctioned module: services/referral.py. auth.py's
signup handler only ever calls services.referral.record_attribution(),
which writes a 'pending' bookkeeping row and never touches a wallet --
test_auth_py_has_no_credit_wallet_call below still enforces that auth.py
itself never calls credit_wallet directly, which remains true.

This test makes both rules durable: it statically scans backend source for
every call site that could *increase* a wallet balance and asserts the set
of modules doing so is exactly the allowed set, and it scans for the
'referral_bonus' txn_type literal and asserts it appears only where it is
sanctioned to. A future change that adds a new crediting call site, or a
second place paying out a referral bonus, will fail this test until the
allowlists below are deliberately edited -- which is the point: a reviewer
has to see it.

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
#   - services/referral.py : the ONE place that settles a referral reward
#     (settle_on_first_payment(), triggered from payment_endpoints.py after
#     the invitee's first successful payment). Added 2026-08-28 alongside
#     migration 0051; see that module's docstring for the full contract.
ALLOWED_CREDIT_MODULES = frozenset({
    "payment.py",
    "admin_user_ops.py",
    "services/billing.py",
    "services/referral.py",
})

# services/billing.py's credit_wallet() docstring names BOTH txn_type
# strings once each, purely as illustrative examples of the parameter
# ("e.g. ``signup_bonus``, ``referral_bonus``") -- not an actual call.
# services/billing.py is off-limits to this packet (it *defines*
# credit_wallet and is senior/shared-adjacent) so that docstring line
# cannot be edited away here. Both literal-scanning checks below carve
# this one file out for that one reason, rather than either leaving the
# blind spot open (the bug this change fixes) or quietly widening the ban
# to something this packet cannot make true.
_DOCSTRING_EXAMPLE_CARVEOUT = frozenset({"services/billing.py"})

# 'signup_bonus' is fully retired and must never reappear anywhere else --
# the feature it named is gone, full stop, no successor.
REMOVED_TXN_TYPES = ("signup_bonus",)

# 'referral_bonus' is a LIVE txn_type now (not removed), but it is only
# allowed to appear as a literal in services/referral.py -- the one real
# call site (see ALLOWED_CREDIT_MODULES above) -- plus the billing.py
# docstring carve-out. Showing up anywhere else in application code is
# either a careless copy-paste of the old removed feature under its new
# name, or a second, unreviewed payout path -- and this test's job is to
# catch either.
#
# (This test file itself, and the rest of backend/tests/, are never part
# of `sources` -- `_load_backend_sources()` below only reads backend/*.py
# and backend/services/*.py, the application code that actually ships --
# so this file naming the string needs no carve-out of its own.)
REFERRAL_BONUS_TXN_TYPE = "referral_bonus"
REFERRAL_BONUS_ALLOWED_SOURCES = frozenset({"services/referral.py"}) | _DOCSTRING_EXAMPLE_CARVEOUT


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
    """auth.py must not call credit_wallet at all. The old signup gift is
    permanently gone. The referral bonus is real again (owner decision
    2026-08-28), but it is paid on the invitee's first successful payment
    from services/referral.py, not from auth.py -- auth.py's signup handler
    only calls services.referral.record_attribution(), which writes a
    'pending' bookkeeping row and never touches a wallet."""
    text = (BACKEND / "auth.py").read_text(encoding="utf-8")
    assert not _credit_wallet_call_lines(text)


def find_txn_type_violations(
    sources: dict[str, str], txn_types: tuple[str, ...], allowed: frozenset[str],
) -> list[str]:
    """Return a violation string for every (relpath, txn_type) pair where
    `txn_type` appears as a literal substring of `sources[relpath]` and
    `relpath` is not in `allowed`.

    Used two ways in this file: with `allowed=_DOCSTRING_EXAMPLE_CARVEOUT`
    for the fully-retired `REMOVED_TXN_TYPES` (nothing else may ever
    mention them), and with `allowed=REFERRAL_BONUS_ALLOWED_SOURCES` for
    the live-but-confined `REFERRAL_BONUS_TXN_TYPE` (only its one
    sanctioned call site, plus the same docstring carve-out, may mention
    it). Shared logic so both real checks and their canaries below exercise
    one code path, same spirit as `find_wallet_credit_violations`.
    """
    violations: list[str] = []
    for relpath, text in sources.items():
        if relpath in allowed:
            continue
        for txn_type in txn_types:
            if txn_type in text:
                violations.append(f"{relpath}: contains banned txn_type '{txn_type}'")
    return violations


def test_removed_txn_types_do_not_reappear():
    """The retired ledger txn_type literal ('signup_bonus') must not
    resurface anywhere in backend/*.py OR backend/services/*.py under its
    old name -- except the one illustrative docstring mention in
    services/billing.py (see _DOCSTRING_EXAMPLE_CARVEOUT), which this
    packet cannot edit and which is not an actual call site.

    ⚠️ Blind spot closed 2026-08-28: this used to scan only
    `BACKEND.glob("*.py")` (backend/*.py), never backend/services/*.py --
    so a literal 'signup_bonus' or 'referral_bonus' typed into any
    services/ module would have passed this test silently, even though
    `_load_backend_sources()` (used by the credit-site scan above) already
    covered services/*.py. Using that same helper here closes the gap for
    both txn-type checks in this file."""
    sources = _load_backend_sources()
    violations = find_txn_type_violations(sources, REMOVED_TXN_TYPES, _DOCSTRING_EXAMPLE_CARVEOUT)
    assert not violations, "\n".join(violations)


def test_referral_bonus_txn_type_confined_to_sanctioned_sources():
    """'referral_bonus' (unlike 'signup_bonus') is a live txn_type, but only
    services/referral.py actually calls credit_wallet with it -- everywhere
    else it shows up is either the billing.py docstring example (allowed,
    see REFERRAL_BONUS_ALLOWED_SOURCES) or a finding. Scans the same
    backend/*.py + services/*.py sources as the txn-type-removal check
    above, so this shares the same fix for the blind spot noted there."""
    sources = _load_backend_sources()
    violations = find_txn_type_violations(
        sources, (REFERRAL_BONUS_TXN_TYPE,), REFERRAL_BONUS_ALLOWED_SOURCES,
    )
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


def test_canary_detects_signup_bonus_reappearing_in_services():
    """The blind spot this session closed: a 'signup_bonus' literal typed
    into a services/ module (not backend/*.py) must be caught. Before the
    fix, `test_removed_txn_types_do_not_reappear` scanned only
    `BACKEND.glob("*.py")` and this synthetic case would have passed
    silently -- exactly the failure mode the packet flagged at the old
    line 172."""
    synthetic_sources = {
        "services/some_new_feature.py": (
            "REASON = 'sneaky reintroduction'\n"
            "TXN_TYPE = 'signup_bonus'\n"
        ),
    }
    violations = find_txn_type_violations(
        synthetic_sources, REMOVED_TXN_TYPES, _DOCSTRING_EXAMPLE_CARVEOUT,
    )
    assert any("services/some_new_feature.py" in v for v in violations), (
        "Canary failed: the scanner did not flag 'signup_bonus' reappearing "
        "in a synthetic services/ module. The blind spot is still open."
    )


def test_canary_allows_docstring_carveout_even_with_banned_literal():
    """The one reviewed carve-out (services/billing.py's illustrative
    docstring) must actually be suppressed -- otherwise this packet's own
    change would fail its own new test against the real, unedited
    services/billing.py."""
    synthetic_sources = {
        "services/billing.py": "# e.g. \"signup_bonus\", \"referral_bonus\"\n",
    }
    violations = find_txn_type_violations(
        synthetic_sources, REMOVED_TXN_TYPES, _DOCSTRING_EXAMPLE_CARVEOUT,
    )
    assert not violations


def test_canary_detects_referral_bonus_outside_sanctioned_module():
    """A second, unreviewed 'referral_bonus' payout path -- or a careless
    copy-paste of the old removed feature under the live name -- must be
    caught even though 'referral_bonus' itself is no longer banned
    outright."""
    synthetic_sources = {
        "services/some_other_feature.py": (
            "async def sneaky_second_payout(repo, user_id):\n"
            "    await credit_wallet(repo, user_id, Money(1000),\n"
            "        reason='surprise', txn_type='referral_bonus')\n"
        ),
    }
    violations = find_txn_type_violations(
        synthetic_sources, (REFERRAL_BONUS_TXN_TYPE,), REFERRAL_BONUS_ALLOWED_SOURCES,
    )
    assert any("services/some_other_feature.py" in v for v in violations), (
        "Canary failed: the scanner did not flag 'referral_bonus' outside "
        "its sanctioned sources. The confinement check is broken."
    )


def test_canary_allows_referral_bonus_in_its_sanctioned_module():
    """The allowlist for the confined txn_type must actually suppress its
    one real call site -- otherwise this packet's own
    services/referral.py would fail its own new test."""
    synthetic_sources = {
        "services/referral.py": "txn_type='referral_bonus'\n",
    }
    violations = find_txn_type_violations(
        synthetic_sources, (REFERRAL_BONUS_TXN_TYPE,), REFERRAL_BONUS_ALLOWED_SOURCES,
    )
    assert not violations
