"""
Sentry Logs periodic-flush regression tests
=============================================
Sentry Logs (enable_logs=True) batches client-side and is NOT delivered by the
same eager transport as error/issue events — confirmed 2026-08-15 via a live
A/B/C test against the real Sentry ingest API: a one-shot script that logged
once and called sentry_sdk.flush() explicitly delivered every time; a process
that logged once and stayed alive for 90s with NO flush() call never delivered
anything, even after exiting normally. This app's uvicorn process runs forever
and never exits under normal operation, so without a periodic flush, every
logger.info()/.warning() across the whole app accumulates in Sentry's Logs
buffer and never ships. Error/issue capture (Sentry Issues) is unaffected by
any of this — it already shipped immediately without a flush, which is exactly
what made the Logs gap easy to miss in the first place.

These tests are deterministic and make ZERO real network calls — sentry_sdk's
actual flush() is always monkeypatched. The live delivery mechanism itself was
proven separately against the real Sentry API (see this session's commit
message / conversation), not re-verified here; these tests only lock the
app-level scheduling contract so it can't silently regress.

No pytest-asyncio in this repo yet — coroutines are driven with asyncio.run()
directly inside plain sync test functions, matching the rest of the suite's
monkeypatch-based style (see test_accuracy_monitor.py).
"""

from __future__ import annotations

import asyncio

import pytest
import sentry_sdk

from app import main as app_main
from app.core.config import settings


@pytest.fixture(autouse=True)
def _reset_flush_task_state():
    """Every test starts and ends with no leaked background task — app.main's
    _sentry_flush_task is a module-level global shared across the whole test
    session, so a task left running by one test would corrupt the next."""
    app_main._sentry_flush_task = None
    yield
    task = app_main._sentry_flush_task
    if task is not None and not task.done():
        task.cancel()
    app_main._sentry_flush_task = None


def test_startup_hook_is_noop_when_sentry_dsn_unset(monkeypatch):
    """No DSN -> no background task. Starting a flush loop for a Sentry client
    that was never initialized would just be periodic wasted work."""
    monkeypatch.setattr(settings, "SENTRY_DSN", None)
    flush_calls = []
    monkeypatch.setattr(sentry_sdk, "flush", lambda timeout=None: flush_calls.append(timeout))

    asyncio.run(app_main._start_sentry_log_flush_loop())

    assert app_main._sentry_flush_task is None
    assert flush_calls == []


def test_startup_hook_creates_task_when_sentry_dsn_set(monkeypatch):
    """A DSN present -> the periodic loop actually gets scheduled."""
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@example.ingest.sentry.io/1")
    monkeypatch.setattr(sentry_sdk, "flush", lambda timeout=None: None)

    async def _run():
        await app_main._start_sentry_log_flush_loop()
        assert app_main._sentry_flush_task is not None
        assert isinstance(app_main._sentry_flush_task, asyncio.Task)
        assert not app_main._sentry_flush_task.done()

    asyncio.run(_run())


def test_flush_loop_calls_sentry_sdk_flush_periodically(monkeypatch):
    """The actual mechanism under test: the loop must call sentry_sdk.flush()
    on its own, repeatedly, without anything else in the app ever calling it.
    This is the exact behavior that was silently absent in production."""
    monkeypatch.setattr(settings, "SENTRY_LOG_FLUSH_INTERVAL_S", 0.01)
    flush_calls = []
    monkeypatch.setattr(sentry_sdk, "flush", lambda timeout=None: flush_calls.append(timeout))

    async def _run():
        task = asyncio.create_task(app_main._sentry_log_flush_loop())
        try:
            # The loop is infinite by design (it's meant to run for the life of
            # the server) — give it enough wall-clock time to fire several
            # iterations at the patched interval, then cancel.
            await asyncio.sleep(0.1)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())

    assert len(flush_calls) >= 2, (
        f"expected the periodic loop to call sentry_sdk.flush() multiple times in 0.1s at a "
        f"0.01s interval, got {len(flush_calls)} calls — the periodic scheduling regressed."
    )
    assert all(t == 5 for t in flush_calls), "each flush() call should use the same fixed timeout"


def test_flush_loop_survives_a_failing_flush(monkeypatch):
    """A flush() that raises (e.g. a transient network error) must not kill the
    loop — the whole point is this runs for the life of the process, so one
    bad flush should just be logged and retried on the next interval."""
    monkeypatch.setattr(settings, "SENTRY_LOG_FLUSH_INTERVAL_S", 0.01)
    call_count = {"n": 0}

    def _flaky_flush(timeout=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient network error")

    monkeypatch.setattr(sentry_sdk, "flush", _flaky_flush)

    async def _run():
        task = asyncio.create_task(app_main._sentry_log_flush_loop())
        try:
            await asyncio.sleep(0.1)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())

    assert call_count["n"] >= 2, "one failing flush() call must not stop later retries"


def test_shutdown_hook_cancels_task_and_does_a_final_flush(monkeypatch):
    """On shutdown, the periodic task must stop cleanly AND a final flush must
    run — otherwise whatever accumulated since the last periodic tick would be
    stranded when the process exits (a graceful redeploy, not just a crash)."""
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@example.ingest.sentry.io/1")
    monkeypatch.setattr(settings, "SENTRY_LOG_FLUSH_INTERVAL_S", 1000)  # won't fire on its own
    flush_calls = []
    monkeypatch.setattr(sentry_sdk, "flush", lambda timeout=None: flush_calls.append(timeout))

    async def _run():
        await app_main._start_sentry_log_flush_loop()
        task = app_main._sentry_flush_task
        assert task is not None and not task.done()

        await app_main._stop_sentry_log_flush_loop()

        assert app_main._sentry_flush_task is None
        # Give the cancelled task's own cleanup a tick to finish.
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    asyncio.run(_run())

    assert len(flush_calls) == 1, "shutdown must do exactly one final flush, independent of the periodic interval"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
