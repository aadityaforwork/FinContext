"""
A real citation pointing at the wrong number
============================================
THE GAP (2026-09-02): `grounding.citation_validity` proves the address the
model cited exists. It says nothing about what is stored there.

`resolve_source_path()` walked the path and returned a bare bool — it threw
the value away at the end. So a model could write "P/E of 42", cite
`snapshot.pe_ratio`, and score a clean sweep while the context said 18.4:

    grounding.schema_valid       True
    grounding.citation_coverage  1.0
    grounding.citation_validity  1.0     <- the address is real
    grounding.confidence_honest  True
                                         <- nothing compared 42 to 18.4

`grounding.value_match` closes it. Same traversal, but it keeps the value
and compares it against the number the prose actually asserts.

THE DESIGN CONSTRAINT IS FALSE ALARMS, NOT DETECTION. This score feeds
grounding_monitor -> prompt_drafter, so a bogus mismatch can get a prompt
rewritten to chase a phantom. Hence:

  * a claim is only judged when BOTH sides carry a number
  * rounding is correct reporting, not a lie: "3.2%" against a stored 3.24
    passes, because the stored value is rounded to the precision the model
    chose to write
  * when nothing is checkable the score is ABSENT, never 1.0 — a perfect
    score minted from an absence of evidence is worse than no score

Deterministic — no network, no Supabase, no LLM.
"""

from __future__ import annotations

import pytest

from app.services.observability import langfuse_scores as ls

CTX = {
    "snapshot": {"pe_ratio": 18.4, "roe_pct": 22.1, "market_cap_cr": 1850000,
                 "listed_year": 2004, "is_profitable": True, "debt": None},
    "holdings": [{
        "ticker": "TCS",
        "change_percent_today": 3.24,
        "sector_index_return_today": 0.8,
        "news": [{"id": "n1", "headline": "TCS wins $1.2bn multi-year deal"}],
    }],
    "sectors": [{"sector": "IT", "change_percent": 0.8}],
}


def _parsed(text: str, source: str) -> dict:
    """Minimal response carrying one {text, source} claim."""
    return {"movers": [{"attribution": {"text": text, "source": source}}]}


def _vm(text: str, source: str, context=CTX):
    return ls.grounding_scores(_parsed(text, source), context).get("grounding.value_match")


# ---------------------------------------------------------------------------
# The gap itself
# ---------------------------------------------------------------------------
def test_wrong_number_behind_a_valid_citation_is_caught():
    score = _vm("P/E of 42 looks rich", "snapshot.pe_ratio")
    assert score is not None
    assert score.value == 0.0
    assert "42" in score.comment and "18.4" in score.comment


def test_citation_validity_still_passes_the_same_call():
    """The point of the new score: every OTHER check is clean here. If
    citation_validity ever starts failing this case, the two scores have
    become redundant and one of them is wrong."""
    scores = ls.grounding_scores(_parsed("P/E of 42 looks rich", "snapshot.pe_ratio"), CTX)
    assert scores["grounding.citation_validity"].value == 1.0
    assert scores["grounding.citation_coverage"].value == 1.0
    assert scores["grounding.schema_valid"].value is True
    assert scores["grounding.value_match"].value == 0.0


def test_correct_number_passes():
    assert _vm("P/E of 18.4 is fair", "snapshot.pe_ratio").value == 1.0


# ---------------------------------------------------------------------------
# Rounding — the rule that keeps this from crying wolf
# ---------------------------------------------------------------------------
def test_correctly_rounded_number_passes():
    """3.2 against a stored 3.24 is correct reporting. Without this rule
    every sensibly rounded number in the product reads as a fabrication."""
    assert _vm("up 3.2% today", "holdings[0]").value == 1.0


def test_rounding_tolerance_does_not_swallow_a_real_error():
    assert _vm("up 7.9% today", "holdings[0]").value == 0.0


def test_more_precision_than_stored_still_matches():
    assert _vm("P/E of 18.40", "snapshot.pe_ratio").value == 1.0


def test_direction_carried_in_words_is_not_a_mismatch():
    """"fell 3.2%" against a stored -3.24 is normal English. Sign errors are
    a direction question, which the market outcome scores judge far better."""
    ctx = {"h": {"change": -3.24}}
    assert _vm("fell 3.2% on the day", "h", ctx).value == 1.0


# ---------------------------------------------------------------------------
# Where the number lives
# ---------------------------------------------------------------------------
def test_citing_an_object_searches_inside_it():
    """`holdings[0]` is a whole dict. Quoting one of its fields must pass."""
    assert _vm("sector index moved 0.8%", "holdings[0]").value == 1.0


def test_number_inside_a_cited_string_counts():
    """`news[0].headline` resolves to text that genuinely contains a number."""
    assert _vm("a $1.2bn order win", "holdings[0].news[0].headline").value == 1.0


def test_scale_words_are_understood():
    assert _vm("market cap 18,50,000 crore", "snapshot.market_cap_cr").value == 1.0


def test_bps_converts_to_percent():
    ctx = {"rate": {"move_pct": 0.5}}
    assert _vm("tightened 50bps", "rate.move_pct", ctx).value == 1.0


# ---------------------------------------------------------------------------
# Not checkable -> ABSENT, never 1.0
# ---------------------------------------------------------------------------
def test_claim_with_no_number_is_skipped():
    assert _vm("momentum looks strong", "holdings[0]") is None


def test_path_holding_only_text_is_skipped():
    ctx = {"note": {"summary": "sentiment improved"}}
    assert _vm("P/E of 42", "note.summary", ctx) is None


def test_unresolvable_path_is_left_to_citation_validity():
    """Not our failure to report — double-counting one error as two
    violations would make the monitor fire twice for one mistake."""
    scores = ls.grounding_scores(_parsed("P/E of 42", "snapshot.invented_field"), CTX)
    assert scores["grounding.citation_validity"].value == 0.0
    assert "grounding.value_match" not in scores


def test_path_resolving_to_none_is_skipped():
    assert _vm("debt of 500 crore", "snapshot.debt") is None


def test_absent_rather_than_perfect_when_nothing_checkable():
    """The load-bearing distinction. A 1.0 minted from no evidence would be
    read by prompt_monitor as a real signal."""
    scores = ls.grounding_scores(_parsed("momentum looks strong", "holdings[0]"), CTX)
    assert "grounding.value_match" not in scores
    assert scores["grounding.citation_validity"].value == 1.0


# ---------------------------------------------------------------------------
# Things that look like numbers but are not measurements
# ---------------------------------------------------------------------------
def test_bare_year_is_not_treated_as_a_measurement():
    assert _vm("listed back in 2004", "snapshot.pe_ratio") is None


def test_year_alongside_a_real_number_still_checks_the_real_one():
    assert _vm("since 2004 the P/E has been 18.4", "snapshot.pe_ratio").value == 1.0


def test_booleans_are_not_numbers():
    """Python's bool is an int subclass; True must not read as 1."""
    ctx = {"flag": {"is_profitable": True}}
    assert _vm("1 of the checks passed", "flag.is_profitable", ctx) is None


# ---------------------------------------------------------------------------
# Mixed sets and comments
# ---------------------------------------------------------------------------
def test_partial_credit_across_several_claims():
    parsed = {"m": [
        {"a": {"text": "P/E of 42", "source": "snapshot.pe_ratio"}},        # wrong
        {"b": {"text": "ROE 22.1%", "source": "snapshot.roe_pct"}},         # right
        {"c": {"text": "looks strong", "source": "snapshot.pe_ratio"}},     # skipped
    ]}
    score = ls.grounding_scores(parsed, CTX)["grounding.value_match"]
    assert score.value == 0.5, "denominator must be checkable claims only, not all claims"


def test_comment_names_the_stated_and_the_resolved_value():
    """This string becomes grounding_fixtures.violation_detail and then the
    drafter's evidence, so it has to identify the disagreement precisely."""
    c = _vm("P/E of 42 looks rich", "snapshot.pe_ratio").comment
    assert "42" in c
    assert "snapshot.pe_ratio" in c
    assert "18.4" in c


def test_comment_is_length_capped():
    parsed = {"m": [{f"k{i}": {"text": f"P/E of {i + 1}00",
                               "source": "snapshot.pe_ratio"}} for i in range(40)]}
    score = ls.grounding_scores(parsed, CTX)["grounding.value_match"]
    assert score.value == 0.0
    assert len(score.comment) <= 400


# ---------------------------------------------------------------------------
# resolve_source_value — the new primitive
# ---------------------------------------------------------------------------
def test_resolve_source_value_returns_the_value():
    assert ls.resolve_source_value("snapshot.pe_ratio", CTX) == (True, 18.4)
    assert ls.resolve_source_value("holdings[0].ticker", CTX) == (True, "TCS")


def test_resolve_source_value_distinguishes_missing_from_none():
    """A present-but-empty field is honest; a missing one is invented. The
    (found, value) pair is the only way to tell them apart."""
    assert ls.resolve_source_value("snapshot.debt", CTX) == (True, None)
    assert ls.resolve_source_value("snapshot.nope", CTX) == (False, None)


def test_resolve_source_path_still_behaves_exactly_as_before():
    """It's a wrapper now — every old caller must be unaffected."""
    for path, expected in (
        ("snapshot.pe_ratio", True),
        ("snapshot.debt", True),
        ("holdings[0].news[0].headline", True),
        ("holdings[9]", False),
        ("snapshot.invented", False),
        ("", False),
        ("...", False),
    ):
        assert ls.resolve_source_path(path, CTX) is expected, path


@pytest.mark.parametrize("junk", [None, 123, [], {}, "a.b.c", "[0]", "x[[1]]"])
def test_never_raises_on_junk(junk):
    assert ls.resolve_source_value(junk, CTX)[0] is False
    ls.grounding_scores(_parsed("P/E of 42", str(junk)), CTX)


def test_scoring_survives_a_deeply_nested_context():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 42.0}}}}}}}
    ls.grounding_scores(_parsed("value is 42", "a"), deep)  # must not hang or raise


# ---------------------------------------------------------------------------
# Wiring — the score has to actually reach the loop
# ---------------------------------------------------------------------------
def test_a_mismatch_counts_as_a_grounding_violation():
    from app.services.outcomes import outcome_ledger

    assert outcome_ledger._is_grounding_violation(
        "grounding.value_match", {"value": 0.5}) is True
    assert outcome_ledger._is_grounding_violation(
        "grounding.value_match", {"value": 1.0}) is False


def test_the_monitor_watches_it():
    from app.services.pathback import grounding_monitor

    assert "grounding.value_match" in grounding_monitor.VIOLATION_TYPES
