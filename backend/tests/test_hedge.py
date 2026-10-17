"""Tail-latency hedging (services/hedge.py): a slow call gets a second, identical request; the first answer wins."""

import asyncio

import pytest

from app.services.hedge import hedged


def run(coro):
    return asyncio.run(coro)


def maker(delays, results, calls, cancelled):
    """make() whose n-th call sleeps delays[n] and returns (or raises) results[n]."""

    def make():
        n = len(calls)
        calls.append(n)

        async def go():
            try:
                await asyncio.sleep(delays[n])
            except asyncio.CancelledError:
                cancelled.append(n)
                raise
            if isinstance(results[n], BaseException):
                raise results[n]
            return results[n]

        return go()

    return make


def test_a_fast_answer_is_not_hedged():
    calls, cancelled = [], []
    out = run(hedged(maker([0.01], ["one"], calls, cancelled), after=0.5, label="t"))
    assert out == "one" and calls == [0]


def test_a_slow_first_request_is_hedged_and_the_faster_answer_wins():
    calls, cancelled = [], []
    out = run(hedged(maker([1.0, 0.01], ["slow", "fast"], calls, cancelled), after=0.05, label="t"))
    assert out == "fast" and calls == [0, 1] and cancelled == [0]  # the slow one is cancelled, not left running


def test_the_first_request_can_still_win_after_the_hedge_is_sent():
    calls, cancelled = [], []
    out = run(hedged(maker([0.1, 1.0], ["first", "second"], calls, cancelled), after=0.05, label="t"))
    assert out == "first" and calls == [0, 1] and cancelled == [1]


def test_an_early_failure_is_raised_without_a_hedge():
    calls, cancelled = [], []
    with pytest.raises(ValueError, match="bad answer"):
        run(hedged(maker([0.01], [ValueError("bad answer")], calls, cancelled), after=0.5, label="t"))
    assert calls == [0]


def test_one_failure_after_the_hedge_still_returns_the_other_answer():
    calls, cancelled = [], []
    out = run(hedged(maker([0.1, 0.2], [TimeoutError("queue"), "ok"], calls, cancelled), after=0.05, label="t"))
    assert out == "ok" and calls == [0, 1]


def test_both_failing_raises_the_first_error():
    calls, cancelled = [], []
    with pytest.raises(TimeoutError, match="first"):
        run(hedged(maker([0.1, 0.2], [TimeoutError("first"), TimeoutError("second")], calls, cancelled),
                   after=0.05, label="t"))


def test_zero_turns_hedging_off():
    calls, cancelled = [], []
    out = run(hedged(maker([0.1], ["only"], calls, cancelled), after=0, label="t"))
    assert out == "only" and calls == [0]


def test_cancelling_the_caller_cancels_both_requests():
    calls, cancelled = [], []

    async def main():
        task = asyncio.ensure_future(hedged(maker([1.0, 1.0], ["a", "b"], calls, cancelled), after=0.05, label="t"))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)  # let the cancellations land

    run(main())
    assert calls == [0, 1] and sorted(cancelled) == [0, 1]


def test_a_fast_failure_on_the_hedge_does_not_beat_a_slower_success():
    calls, cancelled = [], []
    out = run(hedged(maker([0.2, 0.01], ["ok", RuntimeError("HTTP 429")], calls, cancelled), after=0.05, label="t"))
    assert out == "ok" and calls == [0, 1]


def test_both_failing_reports_the_original_requests_error_even_if_the_hedge_failed_first():
    calls, cancelled = [], []
    with pytest.raises(TimeoutError, match="original"):
        run(hedged(maker([0.2, 0.01], [TimeoutError("original"), RuntimeError("HTTP 429")], calls, cancelled),
                   after=0.05, label="t"))


def test_evolus_agent_error_reply_on_the_hedge_does_not_cancel_the_good_answer(monkeypatch):
    """Review finding (17 Oct): the agent's HTTP 4xx/5xx reply must count as a failure INSIDE the hedge, or a fast
    429 on the second request cancels the original that was about to answer 200."""
    import httpx

    from app import config
    from app.services import evolus, http

    s = config.get_settings()
    for k, v in {"evolus_api_base": "https://evolus.test", "evolus_chat_base": "", "evolus_api_key": "k",
                 "evolus_workspace_id": "w", "evolus_agent_model": "w:agent", "evolus_agent_transport": "openai",
                 "evolus_agent_timeout": 5.0, "atelier_hedge_brain_after": 0.05}.items():
        monkeypatch.setattr(s, k, v)
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        n = len(seen)
        seen.append(n)
        if n == 0:  # the original: slow, then a good answer
            await asyncio.sleep(0.3)
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})
        return httpx.Response(429, json={"title": "rate limited"})  # the hedge: a fast error

    http.set_transport(httpx.MockTransport(handler))
    try:
        value, _meta = run(evolus.agent_chat_json(messages_for_attempt=lambda a: [{"role": "user", "content": "x"}],
                                                  validate=lambda d: d, purpose="test", attempts=1))
    finally:
        http.set_transport(None)
    assert value == {"ok": True} and seen == [0, 1]
