"""Money value object for Multiai billing.

Canonical unit is integer TOMAN (irt). The original codebase uses
``Money(amount)`` where ``amount`` is an integer toman value and reads
``money.irt`` for the integer toman amount. This module preserves that
contract while adding explicit helpers. No floating point is used for money
math.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    """Immutable integer-toman amount."""

    irt: int  # integer tomans

    def __post_init__(self) -> None:
        if not isinstance(self.irt, int):
            raise TypeError(f"Money.irt must be int, got {type(self.irt).__name__}")
        if self.irt < 0:
            raise ValueError(f"Money.irt must be non-negative, got {self.irt}")

    # ── compatibility alias used across the codebase ──
    @property
    def amount(self) -> int:
        return self.irt

    # ── arithmetic ──
    def __add__(self, other: "Money") -> "Money":
        _assert_same(self, other)
        return Money(self.irt + other.irt)

    def __sub__(self, other: "Money") -> "Money":
        _assert_same(self, other)
        if other.irt > self.irt:
            raise ValueError("subtraction would produce negative balance")
        return Money(self.irt - other.irt)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.irt == other.irt

    def __hash__(self) -> int:
        return hash(self.irt)

    def __repr__(self) -> str:
        return f"Money({self.irt} IRT)"

    # ── helpers ──
    def to_toman(self) -> Decimal:
        return Decimal(self.irt)

    def display(self) -> str:
        return f"{self.irt:,} تومان"

    @classmethod
    def from_toman(cls, toman: int | str | Decimal) -> "Money":
        return cls(int(Decimal(str(toman)).quantize(Decimal("1"))))


def _assert_same(a: Money, b: Money) -> None:
    # Both are toman-denominated; no currency mismatch possible by construction.
    if not isinstance(b, Money):
        raise TypeError(f"expected Money, got {type(b).__name__}")
