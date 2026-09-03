"""
Hand-written eval cases for the Langfuse-managed prompts: the two prompts
with market-judged predictions plus portfolio.movers_attribution, which is
judged by deterministic grounding fixtures. See eval_runner.py for the runner these
cases are executed through, and prompt_gate.py (Phase 2) for how two prompt
*versions* get compared against this same set.

Lives in app/services/, not backend/tests/evals/, as of path-back leg 3e:
prompt_drafter.py (a production service, running as a daily job — see its
own module docstring) needs this exact case set to gate its own drafted
candidates, the same way a human running scripts/prompt_gate.py by hand
does. App code importing from the tests/ tree isn't something Render's
deploy is guaranteed to ship or resolve correctly, so the content moved
here — the actual single source of truth — and
`backend/tests/evals/prompt_gate_cases.py` is now a thin re-export kept
only so `scripts/prompt_gate.py` and `test_prompt_gate_live.py` didn't need
to change their import path too.

Each fixture context mirrors the real shape the router builds — see
portfolio_intelligence.py's `tomorrow_input` (tomorrow_watch) and
`annotation_ctx` (news_feed_annotation) — deliberately small (1-2 holdings)
so a case is cheap to run N times, not a realistic full-portfolio payload.

Every `check` is a plain deterministic predicate with a known-correct answer
worked out from the prompt's own stated rules (banned phrases, "no catalyst
-> excluded", "technicals contradict news -> mixed", sector->ticker mapping
for policy items) — no LLM grades anything here.
"""

from __future__ import annotations

from app.services.observability import langfuse_scores
from app.services.pathback.eval_runner import EvalCase

# ---------------------------------------------------------------------------
# portfolio.movers_attribution
# ---------------------------------------------------------------------------
_MOVERS_SCHEMA = """{
  "portfolio_return_today_pct": float | null,
  "top_positive_driver": { "text": str, "source": str } | null,
  "top_negative_driver": { "text": str, "source": str } | null,
  "movers": [
    {
      "ticker": str, "move_percent": float,
      "primary_driver": "stock_specific" | "sector" | "macro" | "flow" | "technical" | "unexplained",
      "attribution": [ { "text": str, "source": str, "weight_pct": int } ],
      "technical_state": {
        "rsi_zone": str | null, "vol_zone": str | null,
        "momentum_state": str | null, "sma_state": str | null,
        "confirms_or_contradicts": str
      }
    }
  ],
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""


def _mover_keeps_useful_resolvable_attribution(result: dict) -> bool:
    movers = result.get("movers") or []
    item = next((m for m in movers if m.get("ticker") == "TESTCO"), None)
    if not item or not item.get("attribution"):
        return False
    scores = langfuse_scores.grounding_scores(result, CASE_MOVERS_CITATION_PATHS.context)
    coverage = scores.get("grounding.citation_coverage")
    validity = scores.get("grounding.citation_validity")
    return bool(coverage and validity and coverage.value == 1.0 and validity.value == 1.0)


CASE_MOVERS_CITATION_PATHS = EvalCase(
    id="movers_attribution.uses_real_context_paths",
    prompt_name="portfolio.movers_attribution",
    context={
        "portfolio_return_today_pct": 1.4,
        "holdings": [{
            "ticker": "TESTCO", "sector": "IT", "change_percent_today": 3.2,
            "sector_index_return_today": 0.8, "excess_return_today": 2.4,
            "mover_bucket": "strong_gainer",
            "news": [{"id": "n1", "source": "Test Wire", "headline": "TESTCO wins export order"}],
            "semantic_news": [],
            "technicals": {"rsi_zone": "strong", "vol_zone": "surge",
                           "momentum_state": "extending_up", "sma_state": "above_sma50"},
        }],
        "market": {"sectors": [{"sector": "IT", "change_percent": 0.8}], "flows": None},
        "india_headlines": [],
    },
    schema_description=_MOVERS_SCHEMA,
    check=_mover_keeps_useful_resolvable_attribution,
    max_tokens=600,
)

def _mover_quotes_the_value_it_cites(result: dict) -> bool:
    """Every number the model states must be the number stored at the path it
    cited. Sibling of the case above, and deliberately not folded into it:
    that one asks "is the address real", this one asks "did you copy the
    right thing off it". A candidate can pass either while failing the other.

    ABSENT SCORE COUNTS AS A FAILURE, which is the whole point of running
    this as a gate case rather than only watching it in production.
    grounding.value_match is omitted when no claim carried a checkable
    number — correct for a live monitor (no evidence, no opinion) but wrong
    here, because "state no numbers at all" would then be the cheapest way
    for a drafted prompt to pass. This context is built so a real
    attribution has a number in it; a candidate that answers without one has
    dodged the question, not satisfied it.
    """
    movers = result.get("movers") or []
    if not next((m for m in movers if m.get("ticker") == "TESTCO"), None):
        return False
    score = langfuse_scores.grounding_scores(
        result, CASE_MOVERS_VALUE_MATCH.context
    ).get("grounding.value_match")
    return bool(score and score.value == 1.0)


CASE_MOVERS_VALUE_MATCH = EvalCase(
    id="movers_attribution.quotes_the_cited_value",
    prompt_name="portfolio.movers_attribution",
    # Numbers here are deliberately awkward — 4.37 / 1.12 / 3.25 rather than
    # round figures — for two reasons. A model reciting a plausible-sounding
    # number instead of reading one gets caught, and the values are far
    # enough apart that quoting the wrong FIELD (sector's 1.12 where the
    # holding's 4.37 belongs) is a mismatch rather than a coincidence.
    # The prompt asks a 'sector' driver to cite excess_return_today, so a
    # correct answer has a number in its prose without being told to add one.
    context={
        "portfolio_return_today_pct": 2.05,
        "holdings": [{
            "ticker": "TESTCO", "sector": "IT", "change_percent_today": 4.37,
            "sector_index_return_today": 1.12, "excess_return_today": 3.25,
            "mover_bucket": "strong_gainer",
            "news": [{"id": "n1", "source": "Test Wire",
                      "headline": "TESTCO wins 1,250 crore export order"}],
            "semantic_news": [],
            "technicals": {"rsi_zone": "strong", "vol_zone": "surge",
                           "momentum_state": "extending_up", "sma_state": "above_sma50"},
        }],
        "market": {"sectors": [{"sector": "IT", "change_percent": 1.12}], "flows": None},
        "india_headlines": [],
    },
    schema_description=_MOVERS_SCHEMA,
    check=_mover_quotes_the_value_it_cites,
    max_tokens=600,
)

MOVERS_ATTRIBUTION_CASES = [CASE_MOVERS_CITATION_PATHS, CASE_MOVERS_VALUE_MATCH]

# ---------------------------------------------------------------------------
# portfolio.tomorrow_watch
# ---------------------------------------------------------------------------
_TOMORROW_SCHEMA = """{
  "per_holding": [
    {
      "ticker": str, "sector": str,
      "catalyst_type": "earnings" | "news" | "technical" | "sector_flow" | "mixed",
      "event_date": str | null, "days_to_event": int | null,
      "what_to_watch": str,
      "direction": "positive" | "negative" | "mixed" | "neutral",
      "importance": "high" | "medium" | "low",
      "sources": [ str ]
    }
  ],
  "macro_themes": [
    {
      "theme": str, "direction": "positive" | "negative" | "mixed",
      "affected_holdings": [ str ], "affected_sectors": [ str ],
      "mechanism": { "text": str, "source": str },
      "importance": "high" | "medium" | "low"
    }
  ],
  "overall_bias": "positive" | "negative" | "neutral",
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

# Zero tolerance forecast phrases (from the prompt's own BANNED list) — a
# grounded, education-not-advice output must never use these regardless of
# how the underlying data reads.
_BANNED_PHRASES = [
    "may pull back", "could lead to", "expected to", "should rise", "poised to",
    "will likely", "price correction", "face downward pressure", "further upside",
    "profit-taking", "breakout candidate",
]


def _no_banned_phrases(result: dict) -> bool:
    text = " ".join(
        [str(w.get("what_to_watch") or "") for w in (result.get("per_holding") or [])]
        + [str((t.get("mechanism") or {}).get("text") or "") for t in (result.get("macro_themes") or [])]
    ).lower()
    return not any(p in text for p in _BANNED_PHRASES)


CASE_TOMORROW_NO_BANNED_PHRASES = EvalCase(
    id="tomorrow_watch.no_banned_forecast_phrases",
    prompt_name="portfolio.tomorrow_watch",
    context={
        "holdings": [{
            "ticker": "TESTCO", "sector": "IT",
            "upcoming_earnings": {"date": "2026-08-17", "days_ahead": 5},
            "semantic_news": [],
            "technicals": {"rsi14": 74, "rsi_zone": "overbought", "vol_zone": "normal",
                            "momentum_state": "extending_up", "sma_state": "above_sma50"},
            "change_percent_today": 1.8,
        }],
        "all_holding_tickers": ["TESTCO"],
        "sector_allocation_today": [{"sector": "IT", "change_percent": 1.1}],
        "india_headlines": [], "global_headlines": [], "market_flows": None,
    },
    schema_description=_TOMORROW_SCHEMA,
    check=_no_banned_phrases,
    max_tokens=500,
)


def _no_catalyst_holding_excluded(result: dict) -> bool:
    tickers = {w.get("ticker") for w in (result.get("per_holding") or [])}
    return "NOCATCO" not in tickers and "TESTCO" in tickers


CASE_TOMORROW_NO_CATALYST_EXCLUDED = EvalCase(
    id="tomorrow_watch.no_catalyst_holding_excluded",
    prompt_name="portfolio.tomorrow_watch",
    context={
        "holdings": [
            {
                "ticker": "TESTCO", "sector": "IT",
                "upcoming_earnings": {"date": "2026-08-17", "days_ahead": 5},
                "semantic_news": [], "technicals": {"rsi_zone": "neutral"},
                "change_percent_today": 0.4,
            },
            {
                # No earnings, no semantic match, no stretched technicals —
                # the prompt's own rule: "If a holding has NO catalyst, do
                # NOT include it."
                "ticker": "NOCATCO", "sector": "FMCG",
                "upcoming_earnings": None, "semantic_news": [],
                "technicals": {"rsi14": 51, "rsi_zone": "neutral", "vol_zone": "normal",
                                "momentum_state": "flat", "sma_state": "above_sma50"},
                "change_percent_today": 0.1,
            },
        ],
        "all_holding_tickers": ["TESTCO", "NOCATCO"],
        "sector_allocation_today": [
            {"sector": "IT", "change_percent": 0.5}, {"sector": "FMCG", "change_percent": 0.1},
        ],
        "india_headlines": [], "global_headlines": [], "market_flows": None,
    },
    schema_description=_TOMORROW_SCHEMA,
    check=_no_catalyst_holding_excluded,
    max_tokens=500,
)

TOMORROW_WATCH_CASES = [CASE_TOMORROW_NO_BANNED_PHRASES, CASE_TOMORROW_NO_CATALYST_EXCLUDED]


# ---------------------------------------------------------------------------
# portfolio.news_feed_annotation
# ---------------------------------------------------------------------------
_NEWS_SCHEMA = """{
  "items": [
    {
      "news_id": str, "headline": str, "source": str,
      "category": "stock_specific" | "sector" | "macro" | "global",
      "impact_level": "high" | "medium" | "low",
      "direction": "positive" | "negative" | "mixed",
      "affected_tickers": [ str ], "reason": str,
      "technical_context": str | null
    }
  ],
  "data_gaps": [ str, ... ]
}"""


def _contradicted_news_is_mixed(result: dict) -> bool:
    items = {it.get("news_id"): it for it in (result.get("items") or [])}
    it = items.get("n1")
    return it is not None and it.get("direction") == "mixed"


CASE_NEWS_TECHNICALS_CONTRADICT_MIXED = EvalCase(
    id="news_feed_annotation.technicals_contradict_news_is_mixed",
    prompt_name="portfolio.news_feed_annotation",
    context={
        "user_holdings": ["TESTCO"], "user_watchlist": [],
        "user_holdings_by_sector": {"IT": ["TESTCO"]},
        "sectors_today": [{"sector": "IT", "change_percent": -0.3}],
        # Rule 10: "If technicals contradict the news, call it 'mixed'."
        # Bullish headline + bearish technicals is the fixture's known-correct
        # trigger for that rule.
        "user_universe_technicals": {
            "TESTCO": {"rsi_zone": "neutral", "vol_zone": "normal",
                       "momentum_state": "extending_down", "sma_state": "below_sma50"},
        },
        "candidate_news": [{
            "id": "n1", "headline": "TESTCO wins large export order, margins seen improving",
            "source": "Test Wire", "scope": "stock_specific", "scope_ticker": "TESTCO",
        }],
    },
    schema_description=_NEWS_SCHEMA,
    check=_contradicted_news_is_mixed,
    max_tokens=500,
)


def _policy_item_mapped_to_sector_holding(result: dict) -> bool:
    items = {it.get("news_id"): it for it in (result.get("items") or [])}
    it = items.get("n2")
    if it is None:
        return False
    return "HDFCBANK" in (it.get("affected_tickers") or [])


CASE_NEWS_POLICY_SECTOR_MAPPING = EvalCase(
    id="news_feed_annotation.policy_item_maps_to_sector_holding",
    prompt_name="portfolio.news_feed_annotation",
    context={
        "user_holdings": ["HDFCBANK"], "user_watchlist": [],
        # Rule 9b: policy items with affected_sectors but no named ticker
        # must be mapped via user_holdings_by_sector -> every matched ticker
        # goes into affected_tickers.
        "user_holdings_by_sector": {"Banking & Finance": ["HDFCBANK"]},
        "sectors_today": [{"sector": "Banking & Finance", "change_percent": 0.6}],
        "user_universe_technicals": {"HDFCBANK": {"rsi_zone": "neutral", "sma_state": "above_sma50"}},
        "candidate_news": [{
            "id": "n2", "headline": "RBI eases priority-sector lending norms for banks",
            "source": "PIB", "scope": "policy_rbi", "scope_ticker": None,
            "affected_sectors": ["Banking & Finance"],
        }],
    },
    schema_description=_NEWS_SCHEMA,
    check=_policy_item_mapped_to_sector_holding,
    max_tokens=500,
)

NEWS_FEED_ANNOTATION_CASES = [CASE_NEWS_TECHNICALS_CONTRADICT_MIXED, CASE_NEWS_POLICY_SECTOR_MAPPING]

ALL_CASES = MOVERS_ATTRIBUTION_CASES + TOMORROW_WATCH_CASES + NEWS_FEED_ANNOTATION_CASES
