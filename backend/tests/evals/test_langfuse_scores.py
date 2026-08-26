"""
Tests for langfuse_scores.py — the deterministic scoring layer.

Everything here runs with NO Langfuse client configured. That's deliberate:
grounding_scores() is a pure function, and the whole point of keeping it
pure is that the scoring logic (the part that can be wrong in a way that
matters) is testable without a network, a vendor account, or a fixture
server. The write path is exercised only for its no-op behaviour.
"""

from __future__ import annotations

from app.services.observability import langfuse_scores as ls

# ---------------------------------------------------------------------------
# resolve_source_path — the first hard check on AGENTS.md rule 2
# ---------------------------------------------------------------------------
CONTEXT = {
    "snapshot": {"roe_pct": 18.2, "pe": None},
    "peers": {"median_pe": 24.1},
    "news": [{"headline": "A"}, {"headline": "B"}, {"headline": "C"}],
    "india_news": [{"headline": "X", "url": "u"}],
}


def test_resolve_plain_and_nested_paths():
    assert ls.resolve_source_path("snapshot.roe_pct", CONTEXT) is True
    assert ls.resolve_source_path("peers.median_pe", CONTEXT) is True


def test_resolve_list_index_and_nested_field():
    assert ls.resolve_source_path("news[2]", CONTEXT) is True
    assert ls.resolve_source_path("india_news[0].headline", CONTEXT) is True


def test_resolve_rejects_invented_field():
    # The failure this whole check exists to catch: a plausible-looking path
    # that names nothing real.
    assert ls.resolve_source_path("snapshot.free_cash_flow_yield", CONTEXT) is False
    assert ls.resolve_source_path("fundamentals.roe", CONTEXT) is False


def test_resolve_rejects_out_of_range_index():
    assert ls.resolve_source_path("news[9]", CONTEXT) is False


def test_resolve_treats_present_but_null_as_valid():
    # A field that exists and is None is honest — the model is supposed to
    # pair that with a data_gaps entry, not be marked as fabricating.
    assert ls.resolve_source_path("snapshot.pe", CONTEXT) is True


def test_resolve_never_raises_on_garbage():
    for bad in ["", "   ", "..", "a..b", "news[", "news[x]", None, 42]:
        assert ls.resolve_source_path(bad, CONTEXT) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# collect_claims — finds {text, source} at any depth, by shape not by name
# ---------------------------------------------------------------------------
def test_collect_claims_finds_nested_claims_regardless_of_field_name():
    parsed = {
        "rationale": [{"text": "a", "source": "snapshot.roe_pct"}],
        "verdict": {"thesis": {"text": "b", "source": "peers.median_pe"}},
        "themes": [{"mechanism": {"text": "c", "source": "news[0]"}}],
        "unrelated": ["just a string", 5],
    }
    claims = ls.collect_claims(parsed)
    assert len(claims) == 3
    assert {c["source"] for c in claims} == {
        "snapshot.roe_pct", "peers.median_pe", "news[0]",
    }


def test_collect_claims_handles_empty_and_scalars():
    assert ls.collect_claims({}) == []
    assert ls.collect_claims(None) == []
    assert ls.collect_claims("string") == []


# ---------------------------------------------------------------------------
# grounding_scores
# ---------------------------------------------------------------------------
def test_parse_failure_scores_schema_invalid_only():
    scores = ls.grounding_scores({}, CONTEXT)
    assert set(scores) == {"grounding.schema_valid"}
    assert scores["grounding.schema_valid"].value is False


def test_clean_response_scores_perfectly():
    parsed = {
        "confidence": "high",
        "data_gaps": [],
        "rationale": [
            {"text": "strong roe", "source": "snapshot.roe_pct"},
            {"text": "cheap vs peers", "source": "peers.median_pe"},
        ],
    }
    s = ls.grounding_scores(parsed, CONTEXT)
    assert s["grounding.schema_valid"].value is True
    assert s["grounding.citation_coverage"].value == 1.0
    assert s["grounding.citation_validity"].value == 1.0
    assert s["grounding.data_gaps"].value == 0.0
    assert s["grounding.confidence_honest"].value is True


def test_invented_citation_drops_validity_below_one():
    parsed = {
        "confidence": "medium",
        "rationale": [
            {"text": "real", "source": "snapshot.roe_pct"},
            {"text": "made up", "source": "snapshot.free_cash_flow_yield"},
        ],
    }
    s = ls.grounding_scores(parsed, CONTEXT)
    assert s["grounding.citation_validity"].value == 0.5
    assert "free_cash_flow_yield" in (s["grounding.citation_validity"].comment or "")


def test_missing_source_drops_coverage():
    parsed = {"rationale": [
        {"text": "sourced", "source": "snapshot.roe_pct"},
        {"text": "bare", "source": ""},
    ]}
    s = ls.grounding_scores(parsed, CONTEXT)
    assert s["grounding.citation_coverage"].value == 0.5
    # Only the sourced claim is eligible for validity checking.
    assert s["grounding.citation_validity"].value == 1.0


def test_high_confidence_with_data_gaps_is_dishonest():
    # Rule 3: "high" only when everything used is actually present.
    parsed = {
        "confidence": "high",
        "data_gaps": ["no earnings date available"],
        "rationale": [{"text": "x", "source": "snapshot.roe_pct"}],
    }
    s = ls.grounding_scores(parsed, CONTEXT)
    assert s["grounding.confidence_honest"].value is False
    assert "data_gaps" in (s["grounding.confidence_honest"].comment or "")


def test_high_confidence_with_bad_citation_is_dishonest():
    parsed = {
        "confidence": "high",
        "data_gaps": [],
        "rationale": [{"text": "x", "source": "nope.not_here"}],
    }
    s = ls.grounding_scores(parsed, CONTEXT)
    assert s["grounding.confidence_honest"].value is False


def test_low_confidence_with_gaps_is_honest():
    # Admitting low confidence while reporting gaps is exactly right.
    parsed = {
        "confidence": "low",
        "data_gaps": ["missing peer medians"],
        "rationale": [{"text": "x", "source": "snapshot.roe_pct"}],
    }
    s = ls.grounding_scores(parsed, CONTEXT)
    assert s["grounding.confidence_honest"].value is True


def test_no_claims_means_no_citation_scores():
    # A response with no {text, source} items (e.g. a pure numeric payload)
    # shouldn't be scored 0.0 on coverage — it should not be scored at all.
    s = ls.grounding_scores({"confidence": "medium", "data_gaps": []}, CONTEXT)
    assert "grounding.citation_coverage" not in s
    assert "grounding.citation_validity" not in s


def test_validity_skipped_without_context():
    parsed = {"rationale": [{"text": "x", "source": "snapshot.roe_pct"}]}
    s = ls.grounding_scores(parsed, None)
    assert "grounding.citation_coverage" in s
    assert "grounding.citation_validity" not in s


# ---------------------------------------------------------------------------
# Write path — must be a silent no-op without a client, never an exception
# ---------------------------------------------------------------------------
def test_write_helpers_noop_without_trace_id():
    assert ls.record_score(None, "x", 1.0) is False
    assert ls.record_grounding_scores(None, {"confidence": "low"}, CONTEXT) == 0
    assert ls.record_outcome_score(None, "1d", hit=True, return_pct=1.2) == 0


def test_flush_never_raises_without_client():
    ls.flush_scores()  # must not raise
