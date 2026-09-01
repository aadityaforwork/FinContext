"""Regression coverage for concurrent news-feed annotation.

The news-feed prompt emits one record per candidate, so its completion time
grows with the number of items. Unlike the fixed-size globe summary, this is
the call shape where sharding produces a measured wall-time win. These tests
also protect the less visible requirement: each prediction must remain joined
to the exact call/context/trace that generated it.
"""

from __future__ import annotations

import asyncio
import threading

from app.routers import portfolio_intelligence as pi


def _candidates(count: int) -> list[dict]:
    return [
        {
            "id": f"candidate[{i}]",
            "headline": f"headline {i}",
            "source": "test",
            "scope": "stock_specific",
        }
        for i in range(count)
    ]


def _run(candidates: list[dict], prompt_meta: dict | None = None):
    return asyncio.run(
        pi._generate_news_annotation_shards(
            "annotate",
            {
                "user_holdings": ["TCS"],
                "user_watchlist": [],
                "candidate_news": candidates,
            },
            '{"items": []}',
            prompt_meta or {
                "name": "portfolio.news_feed_annotation",
                "version": 3,
                "source": "langfuse",
            },
            None,
        )
    )


def test_twenty_candidates_run_as_four_overlapping_calls(monkeypatch):
    barrier = threading.Barrier(4)
    seen_contexts: list[list[str]] = []
    lock = threading.Lock()

    def fake_generate(task, context, schema, max_tokens, temperature,
                      prompt_meta, metrics_out, **kwargs):
        ids = [c["id"] for c in context["candidate_news"]]
        with lock:
            seen_contexts.append(ids)
        # A serial implementation breaks this barrier instead of merely
        # passing a weak call-count assertion.
        barrier.wait(timeout=2)
        metrics_out.update(
            parse_error=False,
            tokens_in=100,
            tokens_out=50,
            duration_ms=25,
            trace_id=f"trace-{ids[0]}",
        )
        return {
            "items": [
                {
                    "news_id": c["id"],
                    "headline": c["headline"],
                    "affected_tickers": ["TCS"],
                }
                for c in context["candidate_news"]
            ],
            "data_gaps": [],
        }

    monkeypatch.setattr(pi.ai_client, "generate_grounded_json", fake_generate)

    data, provenance, records = _run(_candidates(20))

    assert len(records) == 4
    assert len(seen_contexts) == 4
    flattened = [news_id for shard in seen_contexts for news_id in shard]
    assert sorted(flattened) == sorted(c["id"] for c in _candidates(20))
    assert len(flattened) == len(set(flattened)), "candidate shards must be disjoint"
    assert len(data["items"]) == 20
    assert set(provenance) == {c["id"] for c in _candidates(20)}


def test_every_item_keeps_its_exact_call_and_trace(monkeypatch):
    def fake_generate(task, context, schema, max_tokens, temperature,
                      prompt_meta, metrics_out, **kwargs):
        first_id = context["candidate_news"][0]["id"]
        metrics_out.update(parse_error=False, trace_id=f"trace-{first_id}")
        return {
            "items": [{
                "news_id": c["id"],
                "headline": c["headline"],
                "affected_tickers": ["TCS"],
            } for c in context["candidate_news"]],
            "data_gaps": [],
        }

    monkeypatch.setattr(pi.ai_client, "generate_grounded_json", fake_generate)
    _, provenance, records = _run(_candidates(12))

    assert len({record["call_id"] for record in records}) == len(records)
    for news_id, record in provenance.items():
        assert news_id in record["candidate_ids"]
        assert record["metrics"]["trace_id"].startswith("trace-")
        assert record["context"]["candidate_news"]


def test_one_failed_shard_preserves_successful_siblings(monkeypatch):
    def fake_generate(task, context, schema, max_tokens, temperature,
                      prompt_meta, metrics_out, **kwargs):
        ids = [c["id"] for c in context["candidate_news"]]
        if "candidate[0]" in ids:
            raise RuntimeError("provider reset")
        metrics_out.update(parse_error=False, trace_id=f"trace-{ids[0]}")
        return {
            "items": [{
                "news_id": ids[0],
                "headline": "kept",
                "affected_tickers": ["TCS"],
            }],
            "data_gaps": [],
        }

    monkeypatch.setattr(pi.ai_client, "generate_grounded_json", fake_generate)
    data, provenance, records = _run(_candidates(12))

    assert len(records) == 3
    assert len(data["items"]) == 2
    assert len(provenance) == 2
    assert any("1 of 3" in gap for gap in data["data_gaps"])
    failed = next(record for record in records if record["error"])
    assert failed["metrics"]["parse_error"] is True


def test_hallucinated_or_cross_shard_news_id_is_dropped(monkeypatch):
    def fake_generate(task, context, schema, max_tokens, temperature,
                      prompt_meta, metrics_out, **kwargs):
        metrics_out.update(parse_error=False, trace_id="trace")
        return {
            "items": [{
                "news_id": "not-in-this-context",
                "headline": "invented",
                "affected_tickers": ["TCS"],
            }],
            "data_gaps": [],
        }

    monkeypatch.setattr(pi.ai_client, "generate_grounded_json", fake_generate)
    data, provenance, _ = _run(_candidates(6))

    assert data["items"] == []
    assert provenance == {}


def test_small_input_stays_one_call(monkeypatch):
    calls = {"count": 0}

    def fake_generate(task, context, schema, max_tokens, temperature,
                      prompt_meta, metrics_out, **kwargs):
        calls["count"] += 1
        assert max_tokens >= 1000  # enough headroom to close valid JSON
        metrics_out.update(parse_error=False, trace_id="trace")
        return {"items": [], "data_gaps": []}

    monkeypatch.setattr(pi.ai_client, "generate_grounded_json", fake_generate)
    data, _, records = _run(_candidates(5))

    assert calls["count"] == 1
    assert len(records) == 1
    assert data == {"items": [], "data_gaps": []}
