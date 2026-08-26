"""
Langfuse wiring -- traces, scores, datasets, managed prompts.

Named `observability` rather than `langfuse` on purpose: a package
called `langfuse` sitting beside modules that do `from langfuse import
get_client` reads like a shadowing bug even though Python 3's absolute
imports resolve it correctly.

`langfuse_client` owns the singleton every other module borrows.
Deliberately structured metadata + content per the privacy posture in
STRATEGY.md -- check there before adding a new field.
"""
