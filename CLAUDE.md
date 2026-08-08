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
