"""
Agent layer
===========
CrewAI-powered agentic workflows. Heavy LLM workflows (Deep Dive, Portfolio
Intelligence, Context Engine, Narrative-to-Numbers, What-If, Catalyst Radar,
AI Co-Pilot) are implemented as multi-agent crews here.

Architectural rules (enforce throughout):
1. Services compute, agents narrate. Tools in agents/tools.py are thin wrappers
   around services/* — never re-implement math or fetch logic here.
2. Every agent inherits the GROUNDING_CONTRACT from agents.base — no agent is
   allowed to invent numbers. Unsupported fields go to data_gaps.
3. Every crew output is wrapped in app.core.compliance.with_disclaimer at the
   router boundary, not inside the crew.
4. Every crew run is cached via services.llm_cache so we don't burn tokens
   re-running the same analysis on the same data the same day.
5. Crews are composable. Multiple crews can be run in parallel via
   asyncio.gather of their kickoff_async() coroutines.
"""
