"""
LLM calling, caching, tracing and grounding.

`ai_client` is the one entry point for a model call -- it wires in
llm_trace (Langfuse) and the caches. `grounding` builds the CONTEXT
dict that every prompt is grounded in; per AGENTS.md nothing may
reach a prompt that didn't come through it. `embeddings`/`vector_store`
back the semantic news retrieval.
"""
