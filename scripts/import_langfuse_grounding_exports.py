#!/usr/bin/env python3
"""Backfill private grounding transcripts/fixtures from Langfuse JSON exports.

Dry-run is the default. Pass ``--write`` only after Supabase migration 016 has
been applied. The importer recognizes Langfuse-linked prompts plus the legacy
inline Movers task, whose stable prompt name is now
``portfolio.movers_attribution``. Unsupported inline flows are reported and
skipped because the drafter has no versioned prompt + hand-written gate for
them yet.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

GROUNDING_PREFIX = "grounding."
SUPPORTED_PROMPTS = {
    "portfolio.movers_attribution",
    "portfolio.tomorrow_watch",
    "portfolio.news_feed_annotation",
}
_PROMPT_RE = re.compile(
    r"TASK:\s*(.*?)\s*REQUIRED SCHEMA:\s*(.*?)\s*"
    r"CONTEXT \(your only source of truth\):\s*```json\s*(.*?)\s*```",
    re.DOTALL,
)


def _prompt_name(event: dict, task: str) -> str | None:
    name = event.get("promptName") or (event.get("metadata") or {}).get("prompt_name")
    if name in SUPPORTED_PROMPTS:
        return name
    if "mover_bucket is 'strong_gainer'" in task:
        return "portfolio.movers_attribution"
    return None


def _parse_input(raw: object) -> tuple[str, str, dict] | None:
    if not isinstance(raw, str):
        return None
    match = _PROMPT_RE.search(raw)
    if not match:
        return None
    task, schema, context_json = match.groups()
    try:
        context = json.loads(context_json)
    except json.JSONDecodeError:
        return None
    return task.strip(), schema.strip(), context


def _parse_output(raw: object) -> object:
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main() -> int:
    from app.services.outcomes import outcome_ledger

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scores", type=Path)
    parser.add_argument("events", type=Path)
    parser.add_argument(
        "--write", action="store_true", help="Write to private Supabase tables"
    )
    args = parser.parse_args()

    scores = json.loads(args.scores.read_text(encoding="utf-8-sig"))
    events = json.loads(args.events.read_text(encoding="utf-8-sig"))
    scores_by_observation: dict[str, dict] = defaultdict(dict)
    for score in scores:
        name = score.get("name") or ""
        observation_id = score.get("observationId")
        if not observation_id or not name.startswith(GROUNDING_PREFIX):
            continue
        scores_by_observation[observation_id][name] = {
            "value": score.get("value"),
            "data_type": score.get("dataType"),
            "comment": score.get("comment"),
        }

    summary = Counter()
    by_prompt = Counter()
    for event in events:
        observation_id = event.get("id")
        score_map = scores_by_observation.get(observation_id)
        if not score_map:
            continue
        parsed_input = _parse_input(event.get("input"))
        if not parsed_input:
            summary["skipped_unparseable_input"] += 1
            continue
        task, schema, context = parsed_input
        prompt_name = _prompt_name(event, task)
        if not prompt_name:
            summary["skipped_unsupported_prompt"] += 1
            continue

        output = _parse_output(event.get("output"))
        parse_error = not isinstance(output, dict) or not output
        call_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"langfuse-observation:{observation_id}")
        )
        by_prompt[prompt_name] += 1
        summary["eligible"] += 1
        if not args.write:
            continue
        metadata = event.get("metadata") or {}
        ok = outcome_ledger.log_call_metrics(
            prompt_name,
            event.get("promptVersion") or metadata.get("prompt_version"),
            "langfuse_export",
            call_id=call_id,
            context_snapshot=context,
            confidence=(output.get("confidence") if isinstance(output, dict) else None),
            data_gaps_count=(
                len(output.get("data_gaps") or []) if isinstance(output, dict) else None
            ),
            parse_error=parse_error,
            tokens_in=metadata.get("tokens_in"),
            tokens_out=metadata.get("tokens_out"),
            duration_ms=event.get("latencyMs") or metadata.get("duration_ms"),
            trace_id=event.get("traceId"),
            observation_id=observation_id,
            task_text=task,
            schema_description=schema,
            output_snapshot=output,
            grounding_scores=score_map,
            created_at=event.get("startTime"),
            upsert=True,
        )
        summary["written" if ok else "write_failed"] += 1

    mode = "WRITE" if args.write else "DRY RUN"
    print(f"{mode}: {dict(summary)}")
    print(f"By prompt: {dict(by_prompt)}")
    if not args.write:
        print("No database writes made. Apply migration 016, then rerun with --write.")
    return 1 if summary["write_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
