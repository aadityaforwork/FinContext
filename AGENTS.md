# AGENTS.md — FinContext

Instructions for any AI coding agent (Claude Code, Cursor, Codex, etc.) working
in this repo. `CLAUDE.md` points here. Read this before touching anything
under `backend/app/agents/`, `backend/app/services/ai_client.py`,
`backend/app/services/grounding.py`, or any router that calls an LLM.

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
   restated for two calling conventions (raw prompt vs. CrewAI backstory).
   If you change the wording, change it in both places and check they still
   say the same thing.
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
                        keeps it fed.
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

- **Both live crews were silently failing on every single request before
  2026-08-11** — not a latency problem, a correctness one that *presented*
  as latency. Three independent bugs stacked:
  1. `crewai`/`crewai-tools` weren't pinned in `requirements.txt` at all
     despite `agents/base.py` hard-requiring them.
  2. The `[litellm]` extra wasn't installed either — crewai 1.x's `LLM`
     class only talks to a short list of "native" providers out of the box,
     and Groq isn't one of them, so without litellm every kickoff raised
     `ImportError` before even reaching the network.
  3. Even with both installed, crewai 1.15.14 has an **unfixed upstream bug**
     ([crewAIInc/crewAI#5886](https://github.com/crewAIInc/crewAI/issues/5886),
     PR #6355 still open) — every message gets tagged with a
     `cache_breakpoint` key for Anthropic-style prompt caching, but only the
     Anthropic-native adapter strips it back out. The LiteLLM-fallback path
     every non-native provider (Groq included) goes through does not, so the
     raw key reaches Groq's API and Groq's schema validation rejects the
     whole request with a 400.
  Net effect: `narrative_crew.run()` / `risk_brief_crew.run()` would make a
  real network round-trip to Groq, get a 400, get caught by the router's
  `except Exception`, and silently fall back to the legacy `ai_client`
  single-call path — which then made a *second* real LLM call. Every
  narrative-impact/risk-brief request was paying for a failed crew attempt
  **plus** the full legacy call, invisibly, on top of whatever the
  legitimate LLM latency was. This is very likely the real source of "high
  latency" complaints, more so than anything fixable by tuning the crew
  itself. Fixed: `requirements.txt` now pins `crewai[litellm]==1.15.14` +
  `crewai-tools==1.15.14`; `agents/base.py._patch_cache_breakpoint_bug()`
  applies the workaround from the issue thread (no-ops
  `crewai.llms.cache.mark_cache_breakpoint`) — remove it once a released
  crewai version ships the real fix. Verified end-to-end against live Groq:
  narrative crew ~7s, risk-brief crew ~22s, both correctly grounded. Also
  found and fixed a stray `(optional override)` string appended to
  `CREWAI_MODEL` in the local `.env` (not committed — python-dotenv had been
  reading it as part of the model name, which alone was enough to break
  every kickoff independent of the three bugs above; worth checking your own
  `.env` for similar drift if this ever recurs).
  Bump the crewai pin deliberately going forward (major version jumps have
  broken `Crew`/`Task`/`LLM` kwargs before, and this specific bug's fix
  status should be rechecked before any bump) and re-run the eval harness in
  `backend/tests/evals/` before moving it.
- **Adding crewai broke the Render build entirely (2026-08-11, same day as
  the fix above).** Pinning `crewai[litellm]==1.15.14` alongside the
  pre-existing exact pins `fastapi==0.109.2` / `pydantic==2.6.1` made `pip
  install -r requirements.txt` fail with `ResolutionImpossible`: crewai
  requires `pydantic>=2.11.9,<2.13`, and its `mcp` dependency pulls a
  starlette/uvicorn far newer than fastapi 0.109.2 tolerates. A fresh
  `pip install` of just the new package (what got tested before the previous
  fix shipped) doesn't catch this — it silently upgrades pydantic in your
  existing venv instead of failing, which is exactly how this got missed.
  **Always validate a new pin with a full, clean `pip install -r
  requirements.txt` into a fresh venv** (or `uv sync` — see below), not
  `pip install <new-package>` on top of an existing one. Fixed by loosening
  `fastapi`/`uvicorn`/`pydantic` to floors (`pydantic>=2.11.9,<2.13` to stay
  inside crewai's window) and capping `pandas>=2.0.0,<3` (was unpinned and a
  fresh resolve could land on breaking pandas 3.x — same failure shape,
  fixed preemptively). Verified: clean install succeeds, `app.main` imports,
  `app.openapi()` generates, full test suite passes, live narrative-crew
  call against Groq still works, all under the new versions.
  **`backend/pyproject.toml` is a second, separate dependency manifest that
  must be kept in sync by hand** — its own header comment explains why: it
  exists only so Vercel's Python builder (`uv`) has a `[project]` table, and
  once present, Vercel's builder reads *pyproject.toml exclusively*, ignoring
  requirements.txt. It had drifted — still had the exact old pins and never
  got crewai added — so the Vercel backend deploy (`vercel.json`
  `experimentalServices.backend`) would have kept running with agents
  permanently unavailable even after requirements.txt was fixed. Fixed in
  lockstep with requirements.txt, plus regenerated `backend/uv.lock` (`uv
  lock`) and verified with `uv sync` into a throwaway `.venv`.
  **⚠️ That lockstep "fix" then broke Vercel for every deploy after it —
  see the next entry. The two manifests are intentionally NOT identical
  now.** If you change one, think about the other, run `uv lock`, and
  re-verify — but do not blindly mirror them.
- **crewai must NOT be in `backend/pyproject.toml` (2026-08-11, second
  incident).** Adding it there to "fix the drift" above pushed the Vercel
  Python function bundle to **1058 MB against a hard 500 MB platform
  limit**, so every production deploy from `8ec848f` onward failed with
  `Total bundle size exceeds the maximum function size` — including the
  *frontend*, since both services build in one deployment. The last green
  deploy (`e61f5de`) was green precisely *because* pyproject.toml had no
  crewai. The weight is crewai core's RAG/memory stack, which these crews
  never touch: lancedb ~149 MB, googleapiclient ~103 MB, pyarrow ~85 MB,
  chromadb_rust_bindings ~57 MB, onnxruntime ~40 MB, kubernetes ~40 MB.
  `excludeFiles` does not help — it filters source files, not installed
  site-packages. Resolution: crewai stays in `requirements.txt` (Render →
  full agent surfaces) and stays out of `pyproject.toml` (Vercel → the
  lazy `try/except` imports in `agents/base.py`/`registry.py`/`crews/`
  make both crew endpoints fall back to the legacy `ai_client` path, which
  `analysis.py:/narrative-impact` and `risk.py:/risk-brief` already catch
  and log). Measured after the fix: **306.8 MB**, verified by `uv sync`
  into a throwaway env plus a full `app.main` import in that crewai-less
  env (53 routes, `openapi()` generates, `prewarm()` survives).
  Also dropped `crewai-tools` from **both** manifests — nothing in this
  repo ever imported it (`agents/tools.py` uses `crewai.tools`, a core
  submodule, not the separate `crewai_tools` distribution).
  If you want real agents on Vercel, it's an architecture change, not a
  pin: drop `experimentalServices.backend` from `vercel.json` and serve
  the API from Render only.
- **Agent-path latency/TTFR fix (2026-08-11).** `agents/base.py`'s LLM
  singleton used to build lazily on the first real request, so SDK-import +
  client-construction cost landed inside that user's time-to-first-response.
  `main.py`'s startup hook now calls `agents_base.prewarm()` so that cost is
  paid once at boot. `registry._agent()` now also sets `max_iter`/
  `max_execution_time` (`CREWAI_TIMEOUT_SECONDS`/`CREWAI_MAX_ITER`) on every
  agent so a stuck call can't blow up p99, and `make_narrative_extractor`
  opts into `get_llm(fast=True)` (`CREWAI_FAST_MODEL`) since it's a narrow
  extraction step sitting on the critical path of the narrative crew's
  2-call sequential chain. Both live router endpoints
  (`analysis.py:/narrative-impact`, `risk.py:/risk-brief`) still `await` the
  full crew before returning anything — no partial/streaming response yet.
  That's the next lever if TTFR still isn't low enough; it needs a frontend
  contract change (SSE or chunked JSON), not just a backend tweak, so treat
  it as a separate piece of work.
- **No runtime LLM provider fallback.** `ai_client.py` picks OpenAI-or-Groq
  once at import; `agents/base.py` hard-requires `GROQ_API_KEY`. A single
  provider outage currently takes the whole AI surface down. If you're
  touching either file, this is the highest-leverage fix available.
- **Config sprawl.** `ai_client.py`, `agents/base.py`, `vector_store.py`,
  `outcome_ledger.py`, `social.py`, `telegram.py` each do their own
  `load_dotenv()` + `os.getenv()`. `core/config.py` doesn't own AI/Supabase
  vars. Prefer adding new env reads there going forward, even though the
  existing ones haven't been migrated yet.
- **No hallucination regression tests existed before `backend/tests/evals/`
  was added.** `verify_claims()` is a second LLM call asking the model to
  grade itself — a soft check. The eval harness in `backend/tests/evals/`
  is the hard check; extend it before shipping new grounded flows.

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
  never instantiate `Agent(...)` inline in a crew file. If the agent is a
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
