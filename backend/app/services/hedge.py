"""Tail-latency hedging for calls to a shared model queue (AMD Token Factory, directly or through the Evolus agent).

Measured on 17 Oct 2026: the same small Gemma 4 call took 2.4 s, 11.7 s and 34.7 s in a row, and almost all of that
was the wait before the first token (the hosted queue), not generation. A long wait is random, so a second identical
request sent after `after` seconds usually gets through sooner. The first answer wins; the other request is
cancelled. Nothing is made up: both are real calls to the same model, and the winner is the answer used.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

log = logging.getLogger("atelier.hedge")

T = TypeVar("T")


async def hedged(make: Callable[[], Awaitable[T]], *, after: float, label: str) -> T:
    """Run `make()`; if it has not finished after `after` seconds, run it a second time and return whichever
    finishes first successfully. `after` <= 0 disables hedging. A request that fails before `after` raises at once
    (the callers' own retry rules apply). `make()` must RAISE on a failed answer (e.g. an HTTP error status): a
    returned value wins the race. When both fail, the original request's error is raised (so a timeout still reads
    as one, whatever the second request got)."""
    if after <= 0:
        return await make()
    tasks: list[asyncio.Future[T]] = [asyncio.ensure_future(make())]
    try:
        done, _ = await asyncio.wait(tasks, timeout=after)
        if not done:
            log.info("%s: no answer after %.0fs - sending a second, identical request (hedge)", label, after)
            tasks.append(asyncio.ensure_future(make()))
        errors: dict[int, BaseException] = {}
        pending = set(tasks)
        while pending:
            finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in finished:
                err = t.exception()
                if err is None:
                    if len(tasks) > 1:
                        log.info("%s: answered by request %d of 2", label, tasks.index(t) + 1)
                    return t.result()
                errors[tasks.index(t)] = err
        raise errors[min(errors)]  # the original request's error when both failed
    finally:
        for t in tasks:  # the loser, or both when our caller was cancelled
            if not t.done():
                t.cancel()
            elif not t.cancelled():
                t.exception()  # mark a failed loser's error as seen (no "Task exception was never retrieved")
