# CLAUDE.md

See [AGENTS.md](./AGENTS.md) — that's the canonical instructions file for this
repo, kept in the tool-agnostic `AGENTS.md` format so Claude Code, Cursor,
Codex, and anything else pick up the same rules instead of drifting apart.

Everything below is Claude-Code-specific stuff that doesn't belong in
AGENTS.md.

## Project memory

Cross-session facts and prior decisions for this repo are tracked in
`~/.claude/projects/.../memory/` (see `MEMORY.md` there) — compliance
posture, the Supabase RLS fix, etc. Check it before re-deciding something
that's already settled. There's also a `memory/` directory in this repo
(`project_anti_hallucination.md`, `project_context_engine.md`) with
project-local design notes — read those before changing grounding or
context-engine behavior.

## Where to look first

- Product/business roadmap, compliance path, monetization: `STRATEGY.md`
- AI architecture, non-negotiable grounding rules, known gaps: `AGENTS.md`
- Ops scripts (daily outcome scoring, morning brief cron): `scripts/README.md`

## MCP connectors wired to this project

These are connected at the user/account level (claude.ai connectors for
Vercel/Supabase/Notion/Sentry; `~/.claude.json` global `mcpServers` for
context7/puppeteer/langfuse) — nothing to configure per clone, but the IDs
below are project-specific and save a re-discovery round trip. Confirmed
2026-08-09; Langfuse added + Sentry DSN actually wired 2026-08-11.

- **Supabase** — project `FinContext` (`ahfemqxpjnphuxmbgvxc`, ap-south-1,
  Postgres 17). This is *the* project for this repo — there's also an
  unrelated inactive `aadityaforwork's Project` under the same org, don't
  confuse them. Before schema changes, `list_tables` first; before debugging,
  `get_logs`/`get_advisors` before making changes. Every migration/query
  still has to obey [[project_supabase_security_fix]] — `user_id` filter +
  RLS, no `.neq("ticker", "__never__")` global patterns — the MCP doesn't
  relax that rule.
- **Vercel** — project `fin-context` (`prj_8tFKJ4sSZEuv3WTY33jX3WL3hZUo`),
  team `Aaditya's projects` (`team_0zM54x2qnkeYaKt3tP3ALCMq`). A duplicate
  project `fin-context-2h8r` also exists (looks like a stray re-import) —
  not the deploy target, don't push to it. Frontend + `/_/backend` proxy per
  `vercel.json`. Use for deployment status, build logs, runtime
  errors/logs — good first stop when something's broken in prod. Web
  Analytics was already enabled dashboard-side (confirmed via
  `get_web_analytics` returning real 0-counts instead of a not-enabled
  error) but had no code wired up; `@vercel/analytics` + `<Analytics />`
  added to `frontend/src/app/layout.js` 2026-08-11 so pageviews actually get
  tracked. Query with `get_web_analytics` — `mode: "count"` for
  totals, `mode: "aggregate"` grouped by `route`/`country`/etc. Note: the
  Vercel MCP connector still has no general env-var or project-settings
  write tool (see the Sentry/Langfuse entries above) — this one happened to
  already be flipped on, don't assume that pattern holds for other toggles.
- **Sentry** — org `compute-ji`. Two projects: `javascript-nextjs` (frontend,
  pre-existing) and `fincontext-backend` (FastAPI backend, created via MCP
  2026-08-09). DSN fetched via `find_dsns` and wired 2026-08-11:
  `SENTRY_DSN` is set in `backend/.env` for local dev, and (as of some point
  between 2026-08-09 and 2026-08-11 — not done by an agent session, presumably
  set by hand in the dashboard) it's also live in Vercel prod, confirmed via
  the `Sentry initialized (env=production, logs enabled)` boot log line.
  **2026-08-11 "nothing shows up in Sentry" investigation** — three separate
  findings, all fixed:
  - Errors/ingestion were never actually broken — verified by sending a real
    test event straight to the prod DSN, which landed as an issue within
    seconds. If issues still don't show up, the DSN/network path is not the
    suspect; check whether the code path that should error even ran.
  - Traces showed zero because `traces_sample_rate` is `0.1` and there was
    close to zero real traffic — not a bug, expected at that combination.
    Don't raise the sample rate without asking; it was set deliberately (see
    `.env.example`).
  - **Logs were genuinely broken, for two stacked reasons**, both fixed:
    (1) `sentry_sdk.init()` never set `enable_logs` (defaults `False` as of
    sentry-sdk ≥2.35) — added in `main.py`. (2) Independent of Sentry
    entirely: the root Python logger defaults to `WARNING` and nothing in
    this codebase ever raised it, so `logger.info(...)` on any logger other
    than `uvicorn.error`/`uvicorn.access` (which uvicorn configures itself)
    was a silent no-op — never printed to console/Vercel runtime logs
    either, this whole time. Fixed with `logging.basicConfig(level=INFO)` in
    the new `backend/app/__init__.py` (has to run before any `app.*`
    submodule imports — `ai_client.py` logs at import time — so it can't
    live in `main.py` without fighting ruff's import-order rules). Verified
    end-to-end: a stdlib `logger.info()` call now reaches Sentry Logs.
  Use `search_issues`/`analyze_issue_with_seer` to triage before touching
  exception-prone code (LLM provider calls, Supabase queries). Sentry Logs
  indexing lag was ~10-15min on first use, faster (~5min) after — don't
  conclude "broken" from an immediate empty search, retry after a few
  minutes or use `get_sentry_resource(resourceType="event", ...)` on a known
  event ID for a lag-free direct lookup.
- **Langfuse** — LLM observability, project keys in `~/.claude.json` under
  the top-level (user-scope) `mcpServers.langfuse` entry — added 2026-08-11.
  Wired into `backend/app/services/llm_trace.py`'s `span()` context manager,
  so every `ai_client.py` call and every CrewAI crew kickoff (via
  `agents/orchestrator.py`'s `run_cached`) gets a Langfuse generation
  observation automatically — no per-call-site changes needed if you add a
  new AI surface through the existing `llm_trace.span(...)` pattern.
  Deliberately sends structured metadata only (model, provider, tokens,
  confidence, data_gaps) — **not** raw prompt/completion text, per the same
  PII reasoning as `send_default_pii=False` on Sentry (portfolio/financial
  data, no DPA with a third-party host). Keys are in `backend/.env` for
  local dev; not yet set in Vercel prod (same env-var-write gap as Sentry
  above).
- **Notion** — workspace page "FinContext — Engineering Hub" created via MCP
  2026-08-09: https://app.notion.com/p/3b75380d6dcd8179b6f7dc1434c83374 —
  a pointer/index page (infra table + open threads), not a mirror of
  `STRATEGY.md`. Update it when infra changes (new Sentry DSN wired, project
  IDs change) rather than letting it drift.
- **context7** — pull current library docs (FastAPI, Next.js, CrewAI,
  Supabase client, pgvector, Langfuse) instead of relying on training-data
  recall, especially for anything version-sensitive. Prefer this over web
  search for library/API syntax questions.
- **puppeteer** — drive the actual frontend for visual/functional checks
  (e.g. verifying a new AI surface component renders and reads right,
  screenshotting `MorningBrief`/`PeerPulseCard`/etc.) rather than reasoning
  about JSX in the abstract.
