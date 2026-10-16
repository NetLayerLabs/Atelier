"""One money formatter for the backend: amounts are shown in the BRAND currency (Brand workspace profile).

The brand's currency is the unit of every target cost, retail price, guardrail and converted quote. Nothing assumes
USD: `fmt(170, "EUR")` is "€170.00", `fmt(170, "CHF")` is "CHF 170.00", and without a currency the bare number is
shown rather than a guessed symbol.
"""

from __future__ import annotations

from typing import Optional

# Symbols only where they are unambiguous in English-language UI; every other code is written out ("CHF 170.00").
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "₹", "KRW": "₩"}


def brand_currency() -> Optional[str]:
    """The brand currency from the workspace profile (the guardrails carry the same value). None without a profile
    (approving a design needs one, so every run has it)."""
    from . import workspace

    p = workspace.profile()
    return p.currency.upper() if p and p.currency else None


def fmt(x: float, currency: Optional[str], dp: int = 2) -> str:
    """'€1,234.50' · '-$38' · 'CHF 170.00' · '170.00' (no currency known)."""
    ccy = (currency or "").upper().strip()
    num = f"{abs(x):,.{dp}f}"
    sign = "-" if x < 0 and round(abs(x), dp) > 0 else ""
    if not ccy:
        return f"{sign}{num}"
    sym = SYMBOLS.get(ccy)
    return f"{sign}{sym}{num}" if sym else f"{sign}{ccy} {num}"


def brand(x: float, dp: int = 2) -> str:
    """`fmt` in the brand currency."""
    return fmt(x, brand_currency(), dp)
