"""Money value object for Sanjabai billing.

The internal, canonical unit for every ``Money`` amount in this codebase is
integer TOMAN. There is no floating point anywhere in money math.

Iranian payment gateways (Zarinpal etc.) speak Rial (1 Toman = 10 Rial), and
users think in Toman. Converting to/from Rial happens ONLY inside a
payment-gateway adapter at the edge of the system — never here, and never
implicitly. A prior field name (``irt``, which reads as "Iranian Rial") on
this exact class caused a confirmed production bug: the frontend divided the
value by 10 assuming it was Rial. The field is named ``toman`` to make the
unit unambiguous from the name alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    """Immutable integer-toman amount."""

    toman: int  # integer tomans

    def __post_init__(self) -> None:
        if not isinstance(self.toman, int):
            raise TypeError(f"Money.toman must be int, got {type(self.toman).__name__}")
        if self.toman < 0:
            raise ValueError(f"Money.toman must be non-negative, got {self.toman}")

    # ── compatibility alias used across the codebase ──
    @property
    def amount(self) -> int:
        return self.toman

    # ── arithmetic ──
    def __add__(self, other: "Money") -> "Money":
        _assert_same(self, other)
        return Money(self.toman + other.toman)

    def __sub__(self, other: "Money") -> "Money":
        _assert_same(self, other)
        if other.toman > self.toman:
            raise ValueError("subtraction would produce negative balance")
        return Money(self.toman - other.toman)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.toman == other.toman

    def __hash__(self) -> int:
        return hash(self.toman)

    def __repr__(self) -> str:
        return f"Money({self.toman} Toman)"

    # ── helpers ──
    def to_toman(self) -> Decimal:
        return Decimal(self.toman)

    def display(self) -> str:
        return f"{self.toman:,} تومان"

    @classmethod
    def from_toman(cls, toman: int | str | Decimal) -> "Money":
        return cls(int(Decimal(str(toman)).quantize(Decimal("1"))))


def _assert_same(a: Money, b: Money) -> None:
    # Both are toman-denominated; no currency mismatch possible by construction.
    if not isinstance(b, Money):
        raise TypeError(f"expected Money, got {type(b).__name__}")
