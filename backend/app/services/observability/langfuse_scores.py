"""
Langfuse scores — the quality signal that was missing from tracing
=====================================================================
Before this module, Langfuse held our prompts and every call's cost/latency,
but had no idea whether any answer was *good*. The good/worse/no-change
verdict existed only in two places neither of which Langfuse can see: a CLI
report from prompt_gate.py, and Supabase rows read by prompt_monitor.py. So
the tool that owns prompt versions could not show the quality of those
versions. This module closes that: every score we can compute gets written
back onto the trace that produced it.

THREE SOURCES OF TRUTH, IN DESCENDING ORDER OF AUTHORITY:

  1. The market (`outcome.*`) — pushed back a day or more later by
     outcome_ledger.compute_pending_outcomes() once real price action has
     graded a prediction. External, exact, unfakeable. This is the score
     that actually answers "is this prompt version better".
  2. Deterministic grounding checks (`grounding.*`) — computed at call time
     from the parsed response + the CONTEXT it was supposed to cite. Free,
     instant, no LLM. Catches invented citations, missing sources, and
     overclaimed confidence.
  3. Human annotation (`review.*`) — written from Langfuse's own annotation
     queue UI, not by this module. Listed here only so the score namespace
     is documented in one place.

NO LLM JUDGES ANYTHING HERE. Same stance as eval_runner.py: every value
below is a plain deterministic function of data we already have. Langfuse
ships managed LLM-as-judge evaluators; we deliberately don't use them —
AGENTS.md's verification posture is that a model grading its own output is
a soft check (see ai_client.verify_claims), and we have a real oracle in the
market. Adding a judge here would dilute a signal that is currently honest.

THE ONE THAT EARNS ITS KEEP: `grounding.citation_validity`. Non-negotiable
rule 2 says every rationale/pro/con/risk item is `{text, source}` where
`source` names a real CONTEXT path. Until now nothing checked that the path
actually *resolves* — a model could cite "snapshot.roe_pct" on a context
that has no such field and no automated check would notice, because the
only claim-level verification we had was verify_claims(), itself an LLM.
resolve_source_path() below walks the real context dict. It is the first
hard, automated enforcement of rule 2 in this codebase.

Never raises. Every public function swallows its own failures and returns
(or logs) rather than propagating — a scoring failure must never break the
request that produced the score, same stance as llm_trace.py.

Public API:
    grounding_scores(parsed, context) -> dict[str, Score]   # pure, testable
    record_grounding_scores(trace_id, parsed, context, observation_id=None)
    record_outcome_score(trace_id, horizon, hit, return_pct, ...)
    record_score(trace_id, name, value, ...)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.observability import langfuse_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score namespace — keep this list authoritative; it's what the Langfuse UI
# groups by, and what prompt_monitor.py reads back per prompt version.
# ---------------------------------------------------------------------------
# grounding.citation_coverage   NUMERIC 0..1  share of claims carrying a source
# grounding.citation_validity   NUMERIC 0..1  share of cited paths that resolve
# grounding.value_match         NUMERIC 0..1  share of numeric claims quoting the
#                                             value actually stored at their path
#                                             (absent when nothing was checkable)
# grounding.confidence_honest   BOOLEAN       "high" only when nothing is missing
# grounding.data_gaps           NUMERIC >=0   count of self-reported gaps
# grounding.schema_valid        BOOLEAN       response parsed at all
# outcome.hit_<horizon>         BOOLEAN       market said the direction was right
# outcome.return_<horizon>      NUMERIC       actual % move over the horizon
# review.*                      (human, written from the annotation queue UI)

CONFIDENCE_RANK = {"low": 0.0, "medium": 0.5, "high": 1.0}


@dataclass(frozen=True)
class Score:
    """One score ready to be written. Kept as a value object so
    grounding_scores() stays a pure function that tests can assert on without
    a Langfuse client anywhere in the picture."""

    name: str
    value: float | str | bool
    data_type: str  # NUMERIC | CATEGORICAL | BOOLEAN
    comment: str | None = None


# ---------------------------------------------------------------------------
# Citation resolution — does the path the model cited actually exist?
# ---------------------------------------------------------------------------
_PATH_PART = re.compile(r"^([A-Za-z0-9_\-]+)((?:\[\d+\])*)$")
_INDEX = re.compile(r"\[(\d+)\]")


def resolve_source_value(path: str, context: Any) -> tuple[bool, Any]:
    """Walk `path` through `context` and return (found, value_at_path).

    Same traversal resolve_source_path() has always done — this version just
    keeps what it landed on instead of discarding it. That value is what
    `grounding.value_match` needs: knowing the shelf exists is a different
    question from knowing the model copied the right thing off it.

    `found=False` always pairs with `value=None`. Note the reverse is not
    true: a path CAN resolve to a genuine None (see resolve_source_path's
    note on empty-but-present fields), so callers must branch on `found`,
    never on `value is None`.

    Never raises — any malformed path is simply not found.
    """
    if not path or not isinstance(path, str):
        return (False, None)
    try:
        cur = context
        for raw in path.strip().split("."):
            m = _PATH_PART.match(raw.strip())
            if not m:
                return (False, None)
            key, idx_blob = m.group(1), m.group(2)
            if isinstance(cur, dict):
                if key not in cur:
                    return (False, None)
                cur = cur[key]
            else:
                return (False, None)
            for idx in _INDEX.findall(idx_blob or ""):
                if not isinstance(cur, (list, tuple)):
                    return (False, None)
                i = int(idx)
                if i >= len(cur):
                    return (False, None)
                cur = cur[i]
        return (True, cur)
    except Exception:
        return (False, None)


def resolve_source_path(path: str, context: Any) -> bool:
    """True if `path` names something that actually exists in `context`.

    Handles the citation shapes the grounding contract asks for:
        "snapshot.roe_pct"           nested dict access
        "news[2]"                    list index
        "india_news[0].headline"     mixed
        "peers.median_pe"

    Deliberately lenient in one direction and strict in the other: a path
    that resolves to `None` still counts as resolved (the field exists and
    is genuinely empty — that's honest, and the model is supposed to pair it
    with a data_gaps entry), but a path naming a key that isn't there at all
    counts as invalid. Invented field names are the failure we're hunting.

    Never raises — any malformed path is simply invalid.
    """
    return resolve_source_value(path, context)[0]


# ---------------------------------------------------------------------------
# Value matching — did the model copy the RIGHT number off the shelf?
# ---------------------------------------------------------------------------
# citation_validity proves the address exists. It says nothing about whether
# the number in the prose is the number stored there: a model can write "P/E
# of 42", cite snapshot.pe_ratio, and score a perfect 1.0 while the context
# says 18.4. Every other grounding check passes too — the JSON is valid, the
# claim is sourced, the path resolves, the confidence is honest. Nothing
# compares 42 against 18.4. That is the hole this closes.
#
# The whole design problem here is FALSE ALARMS, not detection. Flagging a
# correct claim is worse than missing a wrong one, because the alert feeds
# grounding_monitor -> prompt_drafter, and a prompt rewritten to chase a
# phantom mismatch is a real regression. Hence the conservative rule below.

# A number as it appears in prose, with an optional scale/unit suffix.
_NUM_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9_.])"                       # not mid-identifier / mid-decimal
    r"(-?\d{1,3}(?:,\d{2,3})+|-?\d+)"           # 1,23,456 / 1,234 / 1234
    r"(\.\d+)?"                                 # optional decimals
    r"\s*"
    r"(%|pp|bps|crore|cr|lakhs|lakh|billion|bn|million|mn|trillion|tn|k)?",
    re.IGNORECASE,
)

# Multipliers for the scale words that actually show up in Indian market
# copy. `bps` is handled separately — it is a unit conversion (50bps = 0.5%),
# not a magnitude, so it produces an extra candidate rather than replacing.
_SCALE = {
    "crore": 1e7, "cr": 1e7,
    "lakh": 1e5, "lakhs": 1e5,
    "billion": 1e9, "bn": 1e9,
    "million": 1e6, "mn": 1e6,
    "trillion": 1e12, "tn": 1e12,
    "k": 1e3,
}

_MAX_CONTEXT_NUMBERS = 400   # ceiling per claim, so a huge cited node can't stall scoring


@dataclass(frozen=True)
class _Stated:
    """One number as the model wrote it, plus every reading of it we'd accept."""

    raw: str
    decimals: int          # how precisely it was written — drives rounding tolerance
    candidates: tuple[float, ...]


def _stated_numbers(text: str) -> list[_Stated]:
    """Numbers a claim's prose actually asserts.

    Skips things that are labels rather than measurements — bare 4-digit
    years, and any number written with no decimals and no unit that happens
    to look like a year. Those are never the value being cited, and counting
    them would manufacture mismatches out of "Q2 2026".
    """
    out: list[_Stated] = []
    if not isinstance(text, str):
        return out
    for m in _NUM_IN_TEXT.finditer(text):
        int_part, dec_part, suffix = m.group(1), m.group(2) or "", (m.group(3) or "").lower()
        raw = f"{int_part}{dec_part}"
        try:
            base = float(int_part.replace(",", "") + dec_part)
        except ValueError:
            continue
        decimals = len(dec_part) - 1 if dec_part else 0
        if not suffix and not dec_part and 1900 <= abs(base) <= 2100:
            continue  # a year, not a measurement
        cands = {base}
        if suffix in _SCALE:
            cands.add(base * _SCALE[suffix])
        if suffix == "bps":
            cands.add(base / 100.0)   # 50bps == 0.5%
        out.append(_Stated(raw=raw + (suffix or ""), decimals=decimals,
                           candidates=tuple(sorted(cands))))
    return out


def _context_numbers(value: Any, depth: int = 0, label: str = "") -> list[tuple[str, float]]:
    """Every number reachable from a resolved citation target.

    A citation can point at a scalar (`snapshot.pe_ratio` -> 18.4) or at a
    whole object (`holdings[0]` -> a dict of a dozen fields). Both are legal
    under the grounding contract, so both have to be searched — otherwise
    citing the object and quoting one of its fields would read as a mismatch.

    Strings are mined too: `news[0].headline` resolves to text, and "TCS wins
    $1.2bn order" genuinely contains the number a claim may quote.
    """
    found: list[tuple[str, float]] = []

    def walk(node: Any, d: int, lbl: str) -> None:
        if d > 4 or len(found) >= _MAX_CONTEXT_NUMBERS:
            return
        if isinstance(node, bool):
            return                                   # True/False are not measurements
        if isinstance(node, (int, float)):
            found.append((lbl, float(node)))
        elif isinstance(node, str):
            for s in _stated_numbers(node):
                for c in s.candidates:
                    found.append((lbl, c))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, d + 1, f"{lbl}.{k}" if lbl else str(k))
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, d + 1, f"{lbl}[{i}]")

    try:
        walk(value, depth, label)
    except Exception:
        logger.exception("_context_numbers walk failed")
    return found


def _agrees(stated: _Stated, actual: float) -> bool:
    """Would a careful human call this the same number?

    Three ways to agree, in order of how often they matter:

      1. Exactly equal.
      2. The model rounded. "3.2%" against a stored 3.24 is CORRECT
         reporting, not a fabrication — so the stored value is rounded to
         the precision the model chose to write before comparing. This is
         the single most important rule here; without it every sensibly
         rounded number reads as a lie.
      3. Float noise — a hair of relative tolerance.

    Sign is compared loosely on purpose: prose carries direction in words
    ("fell 3.2%" against a stored -3.2), so magnitude agreement counts. A
    genuinely inverted sign is a direction error, which the market outcome
    scores already judge far more authoritatively than string matching could.
    """
    for cand in stated.candidates:
        for c, a in ((cand, actual), (abs(cand), abs(actual))):
            if c == a:
                return True
            if round(a, stated.decimals) == round(c, stated.decimals):
                return True
            if a != 0 and abs(c - a) / abs(a) <= 0.005:
                return True
    return False


def value_match_score(claims: list[dict], context: Any) -> Score | None:
    """Share of checkable numeric claims that quoted the right number.

    CHECKABLE means both sides carry a number: the prose asserts one, and the
    cited path resolves to something containing at least one. Anything else is
    skipped rather than counted — a claim with no numbers is not evidence of
    anything, and neither is one citing a path that holds only text.

    Returns None when nothing was checkable. That is deliberate and matches
    citation_validity's behaviour: emitting 1.0 for "we found nothing to
    check" would launder an absence of evidence into a perfect score, and
    prompt_monitor would then read it as a real signal.

    KNOWN AND ACCEPTED FALSE POSITIVE: a derived number. "beat its sector by
    2.4pp" where 3.2 - 0.8 = 2.4 cites a real path, states a correct number,
    and matches nothing stored there. We do not try to re-derive arithmetic —
    that way lies a checker nobody can reason about. The comment names the
    exact stated-vs-resolved pair so a human can dismiss it in seconds, and
    the monitor's threshold is set well above zero for exactly this reason.
    """
    checkable = 0
    mismatches: list[str] = []

    for claim in claims:
        path = str(claim.get("source") or "").strip()
        if not path:
            continue
        stated = _stated_numbers(claim.get("text"))
        if not stated:
            continue                      # no number asserted — nothing to check
        found, value = resolve_source_value(path, context)
        if not found:
            continue                      # citation_validity's job, not ours
        actuals = _context_numbers(value, label=path)
        if not actuals:
            continue                      # cited a non-numeric field — not checkable

        checkable += 1
        unmatched = [s for s in stated if not any(_agrees(s, a) for _lbl, a in actuals)]
        if unmatched:
            near = ", ".join(f"{lbl}={a:g}" for lbl, a in actuals[:3])
            mismatches.append(
                f"said {'/'.join(s.raw for s in unmatched)} citing {path} (holds {near})"
            )

    if not checkable:
        return None

    matched = checkable - len(mismatches)
    return Score(
        "grounding.value_match",
        round(matched / checkable, 3),
        "NUMERIC",
        None if not mismatches else (
            f"{len(mismatches)}/{checkable} numeric claims disagree with the cited value: "
            + "; ".join(mismatches[:5])
        )[:400],
    )


def collect_claims(parsed: Any) -> list[dict]:
    """Every `{text, source}` object anywhere in the response, at any depth.

    Walks the whole structure rather than looking at known list names
    (rationale/pros/cons/risks/...). New grounded surfaces invent new field
    names all the time; the contract they all share is the claim object
    shape, so that's what we key on. Never raises.
    """
    found: list[dict] = []

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(node, dict):
            if "text" in node and "source" in node:
                found.append(node)
            for v in node.values():
                walk(v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v, depth + 1)

    try:
        walk(parsed)
    except Exception:
        logger.exception("collect_claims walk failed")
    return found


def grounding_scores(parsed: dict | None, context: dict | None) -> dict[str, Score]:
    """Deterministic quality scores for one grounded call. Pure function —
    no network, no client, no side effects. Returns {} for nothing scoreable.

    A parse failure (parsed == {} or None, the shape
    ai_client.generate_grounded_json returns on bad JSON) yields exactly one
    score: schema_valid=False. That case matters more than it looks — a
    failed call writes no ai_predictions rows at all, so without this score
    a prompt version that started emitting unparseable JSON would show up in
    Langfuse as simply *fewer* traces, not as worse ones.
    """
    scores: dict[str, Score] = {}
    if not parsed:
        scores["grounding.schema_valid"] = Score(
            "grounding.schema_valid", False, "BOOLEAN",
            "response did not parse as JSON",
        )
        return scores

    scores["grounding.schema_valid"] = Score("grounding.schema_valid", True, "BOOLEAN")

    gaps = parsed.get("data_gaps") if isinstance(parsed, dict) else None
    gap_count = len(gaps) if isinstance(gaps, (list, tuple)) else 0
    scores["grounding.data_gaps"] = Score(
        "grounding.data_gaps", float(gap_count), "NUMERIC",
        None if not gap_count else "; ".join(str(g) for g in list(gaps)[:5])[:400], # type: ignore
    )

    claims = collect_claims(parsed)
    sourced = [c for c in claims if str(c.get("source") or "").strip()]
    if claims:
        scores["grounding.citation_coverage"] = Score(
            "grounding.citation_coverage",
            round(len(sourced) / len(claims), 3),
            "NUMERIC",
            f"{len(sourced)}/{len(claims)} claims carry a source",
        )

    validity = None
    if sourced and isinstance(context, dict):
        bad = [str(c.get("source")) for c in sourced
               if not resolve_source_path(str(c.get("source")), context)]
        validity = round((len(sourced) - len(bad)) / len(sourced), 3)
        scores["grounding.citation_validity"] = Score(
            "grounding.citation_validity", validity, "NUMERIC",
            None if not bad else "unresolvable: " + ", ".join(sorted(set(bad))[:8])[:400],
        )

        # Sibling to the check above, and the reason it isn't redundant:
        # citation_validity proves the address exists, this proves the model
        # copied the right thing off it. Omitted entirely (not zero, not one)
        # when no claim was checkable — see value_match_score.
        vm = value_match_score(sourced, context)
        if vm is not None:
            scores["grounding.value_match"] = vm

    # Rule 3: "high" is only allowed when every field used is actually in
    # context. We approximate "every field used" as "every citation resolves
    # and the model itself reported no gaps" — both directly observable.
    confidence = str(parsed.get("confidence") or "").lower() or None
    if confidence:
        honest = True
        why = None
        if confidence == "high":
            if gap_count:
                honest, why = False, f"claimed high confidence with {gap_count} data_gaps"
            elif validity is not None and validity < 1.0:
                honest, why = False, "claimed high confidence with unresolvable citations"
        scores["grounding.confidence_honest"] = Score(
            "grounding.confidence_honest", honest, "BOOLEAN", why,
        )

    return scores


# ---------------------------------------------------------------------------
# Writing to Langfuse
# ---------------------------------------------------------------------------
def record_score(
    trace_id: str | None,
    name: str,
    value: float | str | bool,
    *,
    data_type: str | None = None,
    comment: str | None = None,
    observation_id: str | None = None,
    metadata: dict | None = None,
    flush: bool = True,
) -> bool:
    """Write one score onto an existing trace. Returns True if it was sent.

    `flush` defaults True for the same reason llm_trace.span flushes: the
    backend runs as a serverless function that can be frozen the moment a
    response is sent, before the SDK's background batching thread is ever
    scheduled. Batch callers (the daily outcome job, which writes hundreds)
    should pass flush=False and flush once at the end — see
    flush_scores().
    """
    if not trace_id:
        return False
    client = langfuse_client.get_client()
    if client is None:
        return False
    try:
        client.create_score(
            name=name,
            value=value,  # type: ignore[arg-type]
            trace_id=trace_id,
            observation_id=observation_id,
            data_type=data_type,  # type: ignore[arg-type]
            comment=comment,
            metadata=metadata,
        )
        if flush:
            client.flush()
        return True
    except Exception:
        logger.exception("langfuse_scores: create_score(%r) failed", name)
        return False


def flush_scores() -> None:
    """Flush pending scores. For batch writers that passed flush=False."""
    client = langfuse_client.get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.exception("langfuse_scores: flush failed")


def record_grounding_scores(
    trace_id: str | None,
    parsed: dict | None,
    context: dict | None,
    *,
    observation_id: str | None = None,
    flush: bool = True,
) -> int:
    """Compute and write the deterministic call-time scores. Returns how many
    landed. No-op (0) without a trace_id or a Langfuse client."""
    if not trace_id:
        return 0
    scores = grounding_scores(parsed, context)
    if not scores:
        return 0
    written = 0
    for s in scores.values():
        if record_score(
            trace_id, s.name, s.value,
            data_type=s.data_type, comment=s.comment,
            observation_id=observation_id, flush=False,
        ):
            written += 1
    if flush and written:
        flush_scores()
    return written


def record_outcome_score(
    trace_id: str | None,
    horizon: str,
    *,
    hit: bool | None,
    return_pct: float | None,
    ticker: str | None = None,
    direction: str | None = None,
    flush: bool = False,
) -> int:
    """Push the market's verdict back onto the trace that made the call.

    This is the delayed half of the loop and the whole reason trace ids are
    persisted alongside predictions: the call happened yesterday (or twenty
    trading days ago), the answer arrives now, and it has to find its way
    back to the right trace. Once these land, Langfuse can group hit rate by
    `prompt_version` natively — which is the question this whole module
    exists to answer.

    `hit` is None for "mixed"-direction predictions, which the ledger
    deliberately doesn't grade; we still record the realised return so the
    trace isn't silently unscored. Defaults to flush=False because the
    caller is the daily batch job.
    """
    if not trace_id:
        return 0
    comment = " ".join(p for p in [ticker, direction, f"@{horizon}"] if p) or None
    written = 0
    if hit is not None:
        if record_score(trace_id, f"outcome.hit_{horizon}", bool(hit),
                        data_type="BOOLEAN", comment=comment, flush=False):
            written += 1
    if return_pct is not None:
        if record_score(trace_id, f"outcome.return_{horizon}", float(return_pct),
                        data_type="NUMERIC", comment=comment, flush=False):
            written += 1
    if flush and written:
        flush_scores()
    return written
