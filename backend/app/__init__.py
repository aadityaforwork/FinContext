"""
app package init — runs before any submodule (routers/, services/, core/,
agents/), which is exactly why the logging config lives here and nowhere
else.

Root logger defaults to WARNING with zero config anywhere in this codebase.
Every `logger.info(...)` call on a logger OTHER than "uvicorn.error"/
"uvicorn.access" (which uvicorn's own bootstrap configures separately) was a
silent no-op: never printed to console/Vercel runtime logs, and — now that
Sentry's logging integration is wired in (enable_logs=True in main.py) —
never reaches Sentry Logs either, since a record that fails the logger's own
isEnabledFor(INFO) check never reaches ANY handler, Sentry's included.

Diagnosed 2026-08-11 while chasing "nothing shows up in Sentry": the DSN/
ingestion/errors pipeline was already fine (verified with a live test
event), but every INFO-level log site in the app — llm_trace.py's per-call
trace lines, ai_client.py's provider-init lines, everything using
`logging.getLogger(__name__)` or a custom name — was being silently dropped
at the source. This has to run before `app.services.ai_client` and friends
import (they log at import time), which is only guaranteed from the package
`__init__.py` — putting it in main.py instead raced the router imports and
also fought ruff's import-order (E402) rules.
"""

import logging

logging.basicConfig(level=logging.INFO)
