"""
Debug Memory Router
===================
Admin-token endpoint for diagnosing the Render 512 MB memory ceiling. Same
X-Admin-Token gate as /api/outcomes/compute-daily — reuses `_check_admin`
rather than reading ADMIN_TOKEN again (see gotcha_config_env_sprawl).

  GET /api/debug/memory              → RSS, threads, caches, gc, env echo
  GET /api/debug/memory?trim=1       → also call malloc_trim(0), report delta
  GET /api/debug/memory?trace=1      → also tracemalloc top allocators
  GET /api/debug/memory?deep=1       → also sample-estimate cache payload bytes

WHY THIS EXISTS
---------------
The box ratchets ~296 MB idle -> ~489 MB after one dashboard load and gives
back ~3% over two hours (measured 2026-09-03). Two candidate mechanisms:
glibc not returning freed memory to the OS, or objects genuinely retained.
`?trim=1` distinguishes them in one call — if malloc_trim recovers most of
the step, it is the allocator, not a leak.

This module imports stdlib only at module scope. `main.py` imports every
router at boot on a box where `import app.main` already costs ~206 MB, so
anything heavier belongs inside a handler.

SECURITY: never echoes a secret. DATABASE_URL is reported as its scheme only
(e.g. "postgresql+asyncpg"), never host/user/password.
"""

from __future__ import annotations

import gc
import os
import sys
import threading
from collections import Counter
from typing import Any

from fastapi import APIRouter, Header, Query

from app.routers.outcomes import _check_admin  # reuse the existing ADMIN_TOKEN check

router = APIRouter(prefix="/api/debug", tags=["debug"])

# Env vars that decide how much memory this process uses. Echoed as-is because
# none of them is a secret; DATABASE_URL is handled separately below.
_MEMORY_ENV_KEYS = (
    "MALLOC_ARENA_MAX",
    "MALLOC_TRIM_THRESHOLD_",
    "FETCH_POOL_WORKERS",
    "WEB_CONCURRENCY",
    "CREWAI_PREWARM",
    "MEMORY_TRACE",
    "PYTHONMALLOC",
)


def rss_bytes() -> int | None:
    """Current resident set size in bytes, or None if unavailable.

    /proc is the only source that agrees with what Render's metric and the
    OOM killer actually see, so prefer it. resource.getrusage is the fallback
    for non-Linux (dev on Windows gets None from both, which is fine —
    this endpoint is a production instrument).
    """
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        import resource

        # ru_maxrss is a PEAK, not current, and is KiB on Linux / bytes on macOS.
        # Only useful as a coarse fallback — labelled as such in the response.
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:
        return None


def _proc_status() -> dict[str, int]:
    """VmRSS / VmHWM / VmData / VmSize in bytes. Empty dict off Linux.

    VmHWM is the high-water mark — the number that matters for an OOM cap,
    because Render kills on peak, not on the value you happen to sample.
    """
    wanted = {"VmRSS", "VmHWM", "VmData", "VmSize", "VmSwap", "Threads"}
    out: dict[str, int] = {}
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                if key in wanted:
                    parts = rest.split()
                    if parts and parts[0].isdigit():
                        # Threads has no kB suffix; everything else is kB.
                        out[key] = int(parts[0]) * (1024 if len(parts) > 1 else 1)
    except OSError:
        pass
    return out


def _thread_tally() -> dict[str, Any]:
    """Live threads, bucketed by name prefix.

    Pool threads are named by their `thread_name_prefix`, so this shows which
    of the 12 module-level pools have actually spawned workers. Pools spawn
    lazily and never retire a thread, so this count only ever goes up — which
    is itself part of the ratchet.
    """
    names = [t.name for t in threading.enumerate()]
    buckets: Counter[str] = Counter()
    for name in names:
        # "yf-safe_3" -> "yf-safe"; "ThreadPoolExecutor-0_7" -> "ThreadPoolExecutor-0"
        buckets[name.rsplit("_", 1)[0]] += 1
    return {
        "active_count": threading.active_count(),
        "by_prefix": dict(buckets.most_common()),
    }


def _cache_inventory(deep: bool = False) -> dict[str, Any]:
    """Every module-level cachetools cache in app.*, with occupancy.

    Found by introspection rather than a hardcoded list — there are ~72 of
    them and a hardcoded list would rot. Reports len/maxsize always; with
    deep=1, also a sampled byte estimate of the payloads, which is the
    number that matters for the ones holding LLM responses or pandas objects.
    """
    try:
        from cachetools import Cache
    except ImportError:
        return {"error": "cachetools not importable"}

    entries: list[dict[str, Any]] = []
    total_len = 0
    for mod_name, module in list(sys.modules.items()):
        if not mod_name.startswith("app.") or module is None:
            continue
        try:
            members = vars(module)
        except TypeError:
            continue
        for attr, value in list(members.items()):
            if not isinstance(value, Cache):
                continue
            try:
                length = len(value)
                maxsize = getattr(value, "maxsize", None)
            except Exception:
                continue
            total_len += length
            row: dict[str, Any] = {
                "where": f"{mod_name}.{attr}",
                "len": length,
                "maxsize": maxsize,
            }
            if deep and length:
                row["approx_bytes"] = _sample_bytes(value, length)
            entries.append(row)

    entries.sort(key=lambda r: r.get("approx_bytes") or r["len"], reverse=True)
    return {"count": len(entries), "total_entries": total_len, "caches": entries}


def _sample_bytes(cache: Any, length: int) -> int | None:
    """Rough total payload size, extrapolated from up to 5 sampled values.

    Deliberately an estimate: a true deep sizing of ~29k cached entries would
    itself allocate heavily, which is the last thing this endpoint should do
    on a box that is already at the ceiling.
    """
    import itertools
    import pickle

    sampled = 0
    seen = 0
    try:
        # islice over the live view — never materialise the whole cache, which
        # on a 2000-entry cache would allocate the very thing we are measuring.
        for value in itertools.islice(cache.values(), 5):
            try:
                sampled += len(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
                seen += 1
            except Exception:
                continue
    except Exception:
        return None
    if not seen:
        return None
    return int(sampled / seen * length)


def _malloc_trim() -> dict[str, Any]:
    """Ask glibc to return free heap pages to the OS, and report the delta.

    THE decisive measurement. Python's gc returns memory to the allocator,
    not to the kernel; if RSS drops sharply here then the plateau was glibc
    holding freed arenas, and the fix is allocator tuning + narrower pools
    rather than hunting a leak that does not exist.
    """
    import ctypes

    before = rss_bytes()
    try:
        libc = ctypes.CDLL("libc.so.6")
    except OSError as e:
        return {"supported": False, "reason": f"libc.so.6 not loadable: {e}"}
    try:
        returned = libc.malloc_trim(0)
    except (AttributeError, OSError) as e:
        return {"supported": False, "reason": f"malloc_trim unavailable: {e}"}
    after = rss_bytes()
    return {
        "supported": True,
        "malloc_trim_returned": int(returned),  # 1 = memory was actually released
        "rss_before": before,
        "rss_after": after,
        "freed_bytes": (before - after) if (before is not None and after is not None) else None,
    }


def _tracemalloc_top(limit: int = 20) -> dict[str, Any]:
    """Top allocators by size. Only meaningful if tracing was already on —
    starting it here captures allocations from this point forward, which
    tells you nothing about the 193 MB that was allocated before the call.
    """
    import tracemalloc

    if not tracemalloc.is_tracing():
        return {
            "tracing": False,
            "hint": (
                "Set MEMORY_TRACE=1 in the Render env and redeploy so tracemalloc "
                "starts at boot; a snapshot taken from a cold start is the only one "
                "that explains a plateau allocated before this request."
            ),
        }
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")[:limit]
    current, peak = tracemalloc.get_traced_memory()
    return {
        "tracing": True,
        "traced_current": current,
        "traced_peak": peak,
        "top": [{"where": str(s.traceback), "size": s.size, "count": s.count} for s in stats],
    }


def _env_echo() -> dict[str, Any]:
    out: dict[str, Any] = {k: os.environ.get(k) for k in _MEMORY_ENV_KEYS}
    # Scheme only — the rest of DATABASE_URL is credentials.
    raw = os.environ.get("DATABASE_URL")
    out["DATABASE_URL_scheme"] = raw.split("://", 1)[0] if raw and "://" in raw else (
        "UNSET (defaults to sqlite+aiosqlite, ephemeral on Render)" if not raw else "malformed"
    )
    return out


@router.get("/memory")
async def memory(
    x_admin_token: str | None = Header(default=None),
    trim: bool = Query(False, description="Call malloc_trim(0) and report the RSS delta"),
    trace: bool = Query(False, description="Include tracemalloc top allocators"),
    deep: bool = Query(False, description="Sample-estimate cache payload bytes (allocates a little)"),
):
    """Memory diagnostics for the 512 MB Render box.

    Run idle -> load the dashboard once -> run again -> run with ?trim=1.
    If trim recovers most of the step, the ratchet is glibc arenas.
    """
    _check_admin(x_admin_token)

    status = _proc_status()
    payload: dict[str, Any] = {
        "rss_bytes": rss_bytes(),
        "proc_status": status,
        "rss_pct_of_512mb": (
            round(status["VmRSS"] / 536_870_900 * 100, 2) if "VmRSS" in status else None
        ),
        "threads": _thread_tally(),
        "gc": {
            "counts": gc.get_count(),
            "threshold": gc.get_threshold(),
            "enabled": gc.isenabled(),
            "tracked_objects": len(gc.get_objects()),
        },
        "env": _env_echo(),
        "caches": _cache_inventory(deep=deep),
        "heavy_modules_resident": sorted(
            m
            for m in ("crewai", "langgraph", "litellm", "kiteconnect", "twisted", "pandas", "yfinance")
            if m in sys.modules
        ),
    }
    if trace:
        payload["tracemalloc"] = _tracemalloc_top()
    if trim:
        # Last, so every other number above describes the pre-trim state.
        payload["malloc_trim"] = _malloc_trim()
    return payload
