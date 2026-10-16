"""v5: real FX for quotes in another currency - the ECB's euro foreign exchange reference rates.

    https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml   (free, no key; published ~16:00 CET on
    TARGET working days; ~30 currencies quoted per 1 EUR)

Cross rates go through the euro: 1 FROM = (EUR->TO) / (EUR->FROM) TO. Rates are cached for
ATELIER_FX_CACHE_HOURS (default 24). If they can't be loaded, `rate()` returns None and the caller keeps the quote in
its own currency and says so - nothing is guessed.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from ..config import get_settings
from .http import async_client

log = logging.getLogger("atelier.fx")

SOURCE = "ECB euro foreign exchange reference rates"
ALIASES = {"RMB": "CNY"}


@dataclass
class Rates:
    date: str
    per_eur: dict[str, float]  # currency -> units per 1 EUR (EUR itself = 1.0)
    fetched: float


_cache: Optional[Rates] = None
_last_error: Optional[str] = None


def clear_cache() -> None:
    global _cache, _last_error
    _cache, _last_error = None, None


def last_error() -> Optional[str]:
    return _last_error


def parse_ecb(xml: str) -> Rates:
    date = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", xml)
    pairs = re.findall(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([\d.]+)['\"]", xml)
    if not date or not pairs:
        raise ValueError("unexpected ECB rates document")
    per = {c: float(r) for c, r in pairs}
    per["EUR"] = 1.0
    return Rates(date=date.group(1), per_eur=per, fetched=time.time())


async def rates() -> Optional[Rates]:
    global _cache, _last_error
    s = get_settings()
    if _cache and time.time() - _cache.fetched < s.atelier_fx_cache_hours * 3600:
        return _cache
    try:
        async with async_client(s.atelier_fx_timeout, follow_redirects=True) as c:
            r = await c.get(s.atelier_fx_url)
            r.raise_for_status()
        _cache = parse_ecb(r.text)
        _last_error = None
    except Exception as e:  # noqa: BLE001
        _last_error = f"{e.__class__.__name__}: {str(e)[:120]}"
        log.warning("FX rates unavailable (%s) - quotes stay in their own currency", _last_error)
        if _cache:  # a stale day-old table is still a real published rate; say which date it is
            return _cache
        return None
    return _cache


async def rate(from_ccy: str, to_ccy: str) -> Optional[tuple[float, str]]:
    """(units of `to` per 1 `from`, reference date) or None when no published rate is available."""
    f = ALIASES.get(from_ccy.upper(), from_ccy.upper())
    t = ALIASES.get(to_ccy.upper(), to_ccy.upper())
    if f == t:
        return 1.0, ""
    r = await rates()
    if r is None or f not in r.per_eur or t not in r.per_eur:
        return None
    return r.per_eur[t] / r.per_eur[f], r.date
