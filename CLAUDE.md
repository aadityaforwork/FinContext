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
context7/puppeteer) — nothing to configure per clone, but the IDs below are
project-specific and save a re-discovery round trip. Confirmed 2026-08-09.

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
  errors/logs — good first stop when something's broken in prod.
- **Sentry** — org `compute-ji`. Two projects: `javascript-nextjs` (frontend,
  pre-existing) and `fincontext-backend` (FastAPI backend, created via MCP
  2026-08-09 — DSN still needs wiring into the backend's env config, see
  "Config sprawl" in `AGENTS.md`; nothing reports there yet). Use
  `search_issues`/`analyze_issue_with_seer` to triage before touching
  exception-prone code (LLM provider calls, Supabase queries).
- **Notion** — workspace page "FinContext — Engineering Hub" created via MCP
  2026-08-09: https://app.notion.com/p/3b75380d6dcd8179b6f7dc1434c83374 —
  a pointer/index page (infra table + open threads), not a mirror of
  `STRATEGY.md`. Update it when infra changes (new Sentry DSN wired, project
  IDs change) rather than letting it drift.
- **context7** — pull current library docs (FastAPI, Next.js, CrewAI,
  Supabase client, pgvector) instead of relying on training-data recall,
  especially for anything version-sensitive. Prefer this over web search for
  library/API syntax questions.
- **puppeteer** — drive the actual frontend for visual/functional checks
  (e.g. verifying a new AI surface component renders and reads right,
  screenshotting `MorningBrief`/`PeerPulseCard`/etc.) rather than reasoning
  about JSX in the abstract.
