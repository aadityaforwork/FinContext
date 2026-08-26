#!/usr/bin/env python
"""
One-time (idempotent) Langfuse scoring setup.
================================================
Creates the score CONFIGS and the human annotation QUEUE that
app/services/langfuse_scores.py writes against.

Why this is a script and not a migration or a startup hook:
  - It's project-level Langfuse configuration, not application state. It has
    to exist once per Langfuse project, not once per deploy, and definitely
    not on every boot (that would burn a network call on a 512 MB box for
    something that changes maybe twice a year — see the Render memory
    budget note in AGENTS.md).
  - There is no MCP tool for score configs, so this is also the documented
    path for recreating them if the project is ever rebuilt.

Score configs matter for two reasons that aren't obvious from the UI:
  1. They give a score a declared type and range, so the Langfuse dashboard
     can chart it correctly instead of guessing from the first value it saw.
  2. An annotation queue REQUIRES at least one score config — a human
     reviewer picks from the configured options rather than free-typing a
     score name, which is what keeps human scores comparable with each other
     over time.

Idempotent: creating a config that already exists is treated as success.
Safe to re-run.

Usage (from repo root, with backend/.env populated):
    backend/venv/Scripts/python.exe scripts/setup_langfuse_scoring.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
load_dotenv(os.path.join(_BACKEND, ".env"))
sys.path.insert(0, _BACKEND)

from app.services.observability import langfuse_client  # noqa: E402

# (name, data_type, min, max, categories, description)
# Mirrors the namespace documented at the top of app/services/langfuse_scores.py —
# keep the two in sync; that module is the authority on what gets written.
SCORE_CONFIGS = [
    ("grounding.citation_validity", "NUMERIC", 0.0, 1.0, None,
     "Share of cited CONTEXT paths that actually resolve. <1 means the model "
     "cited a field that does not exist — the hard version of AGENTS.md rule 2."),
    ("grounding.citation_coverage", "NUMERIC", 0.0, 1.0, None,
     "Share of {text, source} claims that carry a non-empty source."),
    ("grounding.data_gaps", "NUMERIC", 0.0, 50.0, None,
     "Count of gaps the model self-reported. Not a defect on its own — "
     "honest reporting of missing data is the desired behaviour."),
    ("grounding.schema_valid", "BOOLEAN", None, None, None,
     "Did the response parse as JSON at all. False is the only signal a "
     "totally failed call leaves behind."),
    ("grounding.confidence_honest", "BOOLEAN", None, None, None,
     "False when the model claimed high confidence while reporting data "
     "gaps or citing unresolvable paths (AGENTS.md rule 3)."),
    ("outcome.hit_1d", "BOOLEAN", None, None, None,
     "Did the market agree with the predicted direction one trading day "
     "later. Written by the daily outcome job, not at call time."),
    ("outcome.hit_5d", "BOOLEAN", None, None, None, "As outcome.hit_1d, five trading days."),
    ("outcome.hit_20d", "BOOLEAN", None, None, None, "As outcome.hit_1d, twenty trading days."),
    ("outcome.return_1d", "NUMERIC", -100.0, 100.0, None,
     "Realised percentage move over one trading day."),
    ("outcome.return_5d", "NUMERIC", -100.0, 100.0, None, "Realised percentage move, five days."),
    ("outcome.return_20d", "NUMERIC", -100.0, 100.0, None, "Realised percentage move, twenty days."),
    ("eval.pass_rate", "NUMERIC", 0.0, 1.0, None,
     "Pass rate over N reps for one eval case in a dataset run. A rate, not "
     "a boolean, because a single LLM rep can't distinguish flaky from broken."),
    ("review.verdict", "CATEGORICAL", None, None,
     [{"label": "good", "value": 1}, {"label": "acceptable", "value": 0.5},
      {"label": "wrong", "value": 0}],
     "Human judgement from the grounding-review queue. The only score a "
     "person writes; no automated check may ever produce this."),
]

QUEUE_NAME = "grounding-review"
QUEUE_DESCRIPTION = (
    "Human review of grounded AI outputs. Queue a trace here when an automated "
    "score looks wrong or a user complains. Best candidates: "
    "grounding.confidence_honest = false, grounding.citation_validity < 1, and "
    "any outcome.hit_1d = false on a call that claimed high confidence."
)


def main() -> int:
    client = langfuse_client.get_client()
    if client is None:
        print("Langfuse not configured (LANGFUSE_PUBLIC_KEY unset) — nothing to do.")
        return 1

    api = client.api
    config_ids: list[str] = []

    existing: dict[str, str] = {}
    try:
        page = api.score_configs.get()
        for cfg in getattr(page, "data", []) or []:
            existing[cfg.name] = cfg.id
    except Exception as e:
        print(f"  ! could not list existing configs ({e}) — will attempt creates anyway")

    for name, data_type, lo, hi, categories, description in SCORE_CONFIGS:
        if name in existing:
            config_ids.append(existing[name])
            print(f"  = {name} (exists)")
            continue
        try:
            kwargs: dict = {"name": name, "data_type": data_type, "description": description}
            if lo is not None:
                kwargs["min_value"] = lo
            if hi is not None:
                kwargs["max_value"] = hi
            if categories is not None:
                kwargs["categories"] = categories
            cfg = api.score_configs.create(**kwargs)
            config_ids.append(cfg.id)
            print(f"  + {name}")
        except Exception as e:
            print(f"  ! {name} failed: {e}")

    if not config_ids:
        print("No score configs available — cannot create the annotation queue.")
        return 1

    # NOTE the method names on this client: list_queues / create_queue, not
    # the list/create pattern score_configs uses. Verified against the
    # installed SDK — guessing here is how you get a silent no-op.
    try:
        queues = api.annotation_queues.list_queues()
        if any(q.name == QUEUE_NAME for q in (getattr(queues, "data", []) or [])):
            print(f"  = annotation queue '{QUEUE_NAME}' (exists)")
            return 0
    except Exception:
        pass

    try:
        api.annotation_queues.create_queue(
            name=QUEUE_NAME, description=QUEUE_DESCRIPTION, score_config_ids=config_ids,
        )
        print(f"  + annotation queue '{QUEUE_NAME}' with {len(config_ids)} score configs")
    except Exception as e:
        print(f"  ! annotation queue failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
