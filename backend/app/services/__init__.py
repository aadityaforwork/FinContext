"""
Service layer — grouped by what a module does, not by when it was written.

    marketdata/     external feeds: prices, fundamentals, technicals, news,
                    policy. Knows nothing about users, portfolios or LLMs.
    llm/            model calls, caching, tracing, and grounding. `grounding`
                    builds the CONTEXT every prompt is grounded in.
    outcomes/       the prediction ledger + the grading rule + track record.
                    Source of truth for "was the system right".
    pathback/       the self-iterating prompt loop (legs 3b-3e) that reads
                    outcomes/ and works backwards to a better prompt.
                    Never promotes a prompt — see AGENTS.md rules 8/9.
    observability/  Langfuse wiring: traces, scores, datasets, managed
                    prompts. (Not named `langfuse` — that would sit beside
                    modules doing `from langfuse import ...` and read like a
                    shadowing bug, even though Python 3 resolves it fine.)
    portfolio/      per-user analytics. Everything here is user-scoped and
                    must filter by user_id + rely on RLS.
    notify/         outbound delivery (Telegram, email). Swallows its own
                    failures so a delivery outage can't break a request.

    cache.py        deliberately still top-level: a dependency-free caching
                    primitive used by marketdata/, llm/ and outcomes/ alike.
                    Filing it under any one of them would imply an ownership
                    that doesn't exist.

Rough dependency direction, and it should stay one-way:

    marketdata/  ->  llm/  ->  outcomes/  ->  pathback/
                      |            |             |
                      +---- observability/ ------+

portfolio/ and notify/ sit off to the side; nothing in the chain above
imports them. If you find yourself adding an import that points backwards
along that arrow, the code probably belongs in the earlier package instead.
"""
