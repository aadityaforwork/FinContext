# AGENTS.md — FinContext

Instructions for any AI coding agent (Claude Code, Cursor, Codex, etc.) working
in this repo. `CLAUDE.md` points here. Read this before touching anything
under `backend/app/agents/`, `backend/app/services/ai_client.py`,
`backend/app/services/grounding.py`, or any router that calls an LLM.

**Keeping this file from re-bloating:** before adding a new rule or incident
write-up here, ask two questions. (1) *Can a machine check it?* If yes, it
belongs in `backend/tests/evals/test_agents_md_invariants.py` (or another
test/hook/schema) — leave at most a one-line pointer here, not the prose.
(2) *Is it always true, or only true when touching one area?* Always-true
stays here; area-specific goes in a `memory/*.md` file (see `memory/MEMORY.md`
for the index) and gets a one-line pointer here saying when to read it. This
file should stay something an agent can actually read in full before
starting, not an append-only incident log.

## What this is

FinContext — AI-powered contextual analysis for Indian equities (NSE). FastAPI
backend + Next.js frontend + Supabase (Postgres/pgvector/auth). Product and
compliance context lives in `STRATEGY.md` — read it before proposing new
user-facing AI features or pricing/positioning changes.

## Non-negotiable rules for any AI-surface code

These are the rules that keep this product from becoming a "BUY — target
₹3,500 pulled from thin air" liability. Every one of them exists because the
alternative is a compliance or trust bomb — see `STRATEGY.md` §1/§3.

1. **No LLM call invents a number.** Every numeric claim must trace back to a
   field in a `CONTEXT` dict built by `services/grounding.py` (or a tool
   result, for agents). If a field can't be supported, the model must return
   `null` for it and add an entry to `data_gaps` — never guess.
2. **Every rationale/pro/con/risk item is `{text, source}`.** `source` names
   the exact context path or tool that backs the claim (e.g.
   `"snapshot.roe_pct"`, `"news[2]"`). No bare strings in these lists.
3. **Every grounded output carries a `confidence` field** (`low`/`medium`/`high`).
   `"high"` only if every numeric field used is directly present in context.
4. **Never phrase output as directive advice.** No `BUY`/`SELL` verdicts, no
   target prices, no "you should". The product operates without SEBI
   Research Analyst registration — see `core/compliance.py` and
   `STRATEGY.md` §3. Reframe as signal strength / valuation band / peer rank.
   Every response payload that surfaces a recommendation, score, or
   projected number must go through `with_disclaimer()` from
   `app.core.compliance` before it reaches the client.
5. **The `GROUNDING_CONTRACT` text is duplicated on purpose** in
   `services/ai_client.py` and `agents/base.py` — it's the same doctrine
   restated for two calling conventions (raw prompt vs. CrewAI backstory), not
   byte-identical. If you change the wording, change it in both places —
   `test_agents_md_invariants.py::test_grounding_contract_core_doctrine_present_in_both_copies`
   fails CI if either copy silently drops a rule the other still has.
6. **Deterministic numbers are computed by services, not by the model.**
   `signal_ensemble.py`, `risk_metrics.py`, `technicals.py`,
   `portfolio_analytics.py`, `compute_portfolio_health()` compute real
   numbers with no LLM involved. The LLM's job is to *narrate* those numbers,
   never recompute or re-round them. If you're tempted to have the model
   calculate something numeric, put that calculation in a service instead and
   hand the model the result.
7. **Every Supabase query filters by `user_id` and relies on RLS.** The only
   sanctioned exceptions are backend-only admin-client reads that
   aggregate/anonymize before returning anything to a client — see
   `routers/social.py` (Peer Pulse, k-anonymity floor: ≥5 peer cohort, ≥2
   distinct adders before naming a ticker) and `services/outcome_ledger.py`.
   Never write a query like `.neq("ticker", "__never__")` as a stand-in for
   "all rows" — that pattern has caused a real security bug here before.
8. **Forward promotion of a prompt version is always a human action.** No
   code path may relabel a Langfuse prompt's `production` label to a
   version that wasn't already `production` before — a human decides that,
   every time, by reading a `prompt_gate.py` report and relabeling in the
   Langfuse UI. The one sanctioned exception is `prompt_monitor.py`'s daily
   job, which may *revert* `production` back to the immediately-previous
   live version on measured degradation — never forward, never to a new or
   never-before-live version. This is enforced in code (see that module's
   own docstring + `test_prompt_monitor.py`), not just stated here — don't
   weaken it while "cleaning up" prompt-versioning code.

## Architecture map

```
backend/app/
  routers/            FastAPI endpoints. portfolio_intelligence.py (2200+
                       lines) and analysis.py (850+ lines) are god-files —
                       each owns several unrelated AI flows (movers,
                       morning-brief, news-feed, market-summary, deep-dive,
                       dd-agent, simulator, pre-trade-check). Splitting these
                       is overdue; don't make them bigger without a reason.
  services/
    ai_client.py       Provider-agnostic LLM client (OpenAI → Groq, chosen
                        once at import time — NO runtime fallback yet, see
                        "Known gaps" below). generate_text / generate_json /
                        generate_grounded_json / verify_claims.
    grounding.py        (1250+ lines) Builds the CONTEXT dicts every grounded
                        call cites from: build_stock_context,
                        build_portfolio_context, build_market_context,
                        build_movers_context, build_morning_brief_context.
                        Also owns peer-percentile benchmarking and
                        rule-based (non-LLM) strengths/concerns.
    llm_cache.py         Two-tier cache (in-process TTL + Postgres, shared
                        across workers) for full crew/LLM outputs. Wraps
                        every crew kickoff via agents/orchestrator.run_cached.
    llm_trace.py         Structured per-call tracing (added — see below).
                        Wrap any new LLM/agent call site with
                        `llm_trace.span(...)`.
    langfuse_client.py   Shared lazy Langfuse client (opt-in on
                        LANGFUSE_PUBLIC_KEY, never raises) — used by both
                        llm_trace.py and prompt_registry.py so the client
                        lazy-init lives in one place.
    prompt_registry.py   Path-back leg 3b: fetches Langfuse-managed prompts
                        by `production` label with a hardcoded fallback,
                        never raises. Only wired to the two prompts that
                        produce judged predictions (portfolio_intelligence.py
                        tomorrow-watch + news-feed annotation) — see its
                        module docstring before adding a third call site.
    eval_runner.py        Path-back leg 3b, Phase 1: runs a deterministic-
                        outcome `EvalCase` N times (default 5) and reports a
                        pass rate, not a boolean — no LLM judges anything.
    prompt_gate.py        Path-back leg 3b, Phase 2: offline harness that
                        compares two prompt VERSIONS' text against the same
                        eval-case set and produces a BLOCK/IMPROVED/
                        NO_CHANGE verdict for a human to read. Never
                        promotes, never writes a Langfuse label — see
                        scripts/prompt_gate.py for the CLI.
    prompt_monitor.py      Path-back leg 3b, Phase 3: daily job (see
                        routers/prompt_monitor.py + scripts/run_prompt_
                        monitor.py) comparing the live prompt version's
                        deterministic metrics (prompt_call_log) against the
                        previously-live version. May REVERT `production` to
                        that previous version on measured degradation —
                        never promotes, never labels a new/never-live
                        version. See non-negotiable rule 8 above.
    vector_store.py     pgvector-backed semantic news retrieval
                        (match_news_for_tickers RPC) — surfaces news that
                        affects a ticker even when the headline never names
                        it. Requires SUPABASE_SERVICE_KEY.
    signal_ensemble.py   Deterministic multi-signal conviction scoring (news
                        + technicals + sector + FII/DII flow). Selectivity
                        over coverage — low-conviction calls are dropped,
                        not shown with false confidence.
    outcome_ledger.py    Logs every directional prediction, grades it against
                        actual price moves at 1d/5d/20d, powers the
                        /accuracy page. This is the eval loop — see
                        scripts/compute_outcomes.py for the cron job that
                        keeps it fed. Also owns prompt_call_log (call-grained
                        LLM metrics, feeds prompt_monitor.py) — see that
                        table's own docstring in migration
                        008_prompt_call_log.sql for why it's separate from
                        ai_predictions.
    track_record.py      Path-back leg 1: hierarchical-shrinkage calibration
                        factor from outcome_ledger's judged history, applied
                        to signal_ensemble's conviction. See its module
                        docstring for the shrinkage rationale and the
                        deliberate 1d-horizon trade-off.
  agents/               CrewAI multi-agent framework. PARTIALLY migrated —
                        only 2 of ~7 AI flows run through here:
    registry.py           make_<role>() factories — Agent definitions.
                          Always build a *fresh* Agent per call (CrewAI
                          Agents carry state, aren't safe to share across
                          concurrent crews).
    base.py                GROUNDING_CONTRACT + get_llm() (Groq only —
                          matches the ai_client.py runtime-fallback gap).
    tools.py                @tool wrappers — thin pass-throughs to services/.
                          Never put domain logic here.
    orchestrator.py          run_cached() — cache-around for crew kickoff.
                          run_parallel() — concurrent crew execution.
    crews/narrative.py        LIVE. Narrative-to-Numbers: extractor → quantifier.
    explainers/risk_brief.py  LIVE. Narrates a pre-computed RISK_REPORT.
    (Equity Researcher / Synthesizer in registry.py are stubs — not wired to
    any router yet. Presumably for a future agentic Deep Dive.)
  core/
    compliance.py        Single source of disclaimer text — with_disclaimer().
    config.py             Settings — currently only owns auth/CORS/OAuth vars.
                        AI + Supabase + admin-token env vars are read ad hoc
                        per-module instead (config sprawl — see below).
frontend/src/app/components/
  AnalysisDDAgent / AnalysisSimulator / AnalysisValuation / MorningBrief /
  NewsImpactFeed / PortfolioContextCard / RiskMetricsCard / PeerPulseCard /
  AccuracyView — one component per AI surface. AnalysisVideoPresenter.jsx is
  a browser-TTS narration layer over the existing DD Agent output (no new
  AI call — reuses grounded content, keep it that way).
```

## Known gaps — don't rediscover these, fix them or work around them deliberately

This section used to carry the full incident write-up for each gap inline,
which is exactly the kind of thing that made this file balloon — narrative
history that's only relevant when you're actually touching the affected
area, not every time an agent starts. Full detail now lives in `memory/`,
read on demand; the invariants that came out of the crewai saga are also
hard-tested (see `backend/tests/evals/test_agents_md_invariants.py`), so
regressing them fails CI instead of relying on someone having read this file.

- **CrewAI is wired but fragile across two deploy targets** (Render vs.
  Vercel have different constraints — dependency resolution, a hard 500MB
  function bundle, provider quirks). Read `memory/gotcha_crewai_deploy.md`
  before touching `requirements.txt`, `pyproject.toml`, `agents/base.py`,
  `agents/registry.py`, or `vercel.json`'s `experimentalServices.backend`.
  The short version: crewai lives in `requirements.txt` only, never in
  `pyproject.toml` — `test_agents_md_invariants.py` enforces this.
- **Agent latency (TTFR/prewarm) + no runtime LLM provider fallback.**
  Read `memory/gotcha_agent_runtime.md` before touching `agents/base.py` or
  `ai_client.py`.
- **Config sprawl** — several files each do their own `load_dotenv()` +
  `os.getenv()` instead of going through `core/config.py`. Read
  `memory/gotcha_config_env_sprawl.md` before adding a new env-var read
  anywhere in `backend/app`.
- **Hallucination regression coverage**: `verify_claims()` is a second LLM
  call asking the model to grade itself — a soft check. The eval harness in
  `backend/tests/evals/` is the hard check; extend it before shipping a new
  grounded flow, don't rely on the soft check alone.

## Dev commands

```bash
# backend (from backend/)
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
python -m pytest tests/ -q                      # unit + eval smoke tests

# frontend (from frontend/)
npm install
npm run dev
npm run lint
```

Required env vars: see `backend/.env.example` and `frontend/.env.example`.
At minimum for AI features: one of `OPENAI_API_KEY` / `GROQ_API_KEY`, plus
`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` for anything touching vector store,
outcome ledger, telegram, or social/peer-pulse.

## Conventions worth matching

- Cache keys: `llm_cache.make_key(prefix, *parts)` — deterministic, colon-joined.
- New CrewAI agent: add a `make_<role>()` factory to `agents/registry.py`,
  never instantiate `Agent(...)` inline in a crew file —
  `test_agents_md_invariants.py::test_agent_only_instantiated_in_registry`
  enforces this. If the agent is a
  narrow extraction/classification step (no synthesis, no final verdict)
  and sits on the critical path of a sequential crew, consider
  `_agent(fast=True, ...)` for TTFR — see `agents/base.py` CREWAI_FAST_MODEL.
- New crew whose LLM needs prewarming: it already is — `main.py`'s startup
  hook calls `agents_base.prewarm()`, which builds both the default and
  `fast=True` singletons. Nothing to do per-crew.
- New grounded LLM call outside the agent framework: use
  `ai_client.generate_grounded_json()`, not a raw `chat.completions.create`.
- New AI call site, either system: wrap it in `llm_trace.span("<flow>.<step>", ...)`.
- Every new analytical endpoint response: run it through
  `app.core.compliance.with_disclaimer()` before returning.
