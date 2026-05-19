"""
Portfolio Intelligence Router
==============================
Grounded AI portfolio analysis. All claims reference real holdings data
(P&L, sector weights, concentration flags) from grounding.build_portfolio_context.
High-stakes output goes through a verifier pass.
"""

import asyncio
import gc
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.compliance import with_disclaimer
from app.services import (
    ai_client,
    grounding,
    market_data,
    outcome_ledger,
    response_cache,
    signal_ensemble,
    vector_store,
)
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["portfolio-intelligence"])


class PositionIn(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class IntelRequest(BaseModel):
    positions: list[PositionIn]
    force_refresh: bool = False


class MoversRequest(BaseModel):
    positions: list[PositionIn]
    force_refresh: bool = False


# ---------------------------------------------------------------------------
# Stale-while-revalidate wrapper for SSE endpoints. The two heavy endpoints
# (/portfolio and /movers) take 30-90s for first compute. Wrapping them with
# this cache means:
#   • FRESH window (0-5min)  → cached SSE replay in <500ms
#   • STALE window (5-15min) → cached replay + silent background refresh
#   • MISS                   → full pipeline (still slow but unavoidable)
# Cuts perceived load time on a return visit from 30s → instant.
# ---------------------------------------------------------------------------
SSE_FRESH_TTL_S = 5 * 60     # 5 min
SSE_MAX_TTL_S   = 15 * 60    # 15 min


async def _cached_sse_stream(
    inner_generator,
    cache_key: str,
    *,
    force_refresh: bool = False,
    fresh_ttl_s: int = SSE_FRESH_TTL_S,
    max_ttl_s: int = SSE_MAX_TTL_S,
):
    """Wrap an SSE async-generator with stale-while-revalidate caching.

    Strategy:
      • Cache hit + fresh  → emit cached payload as a single result event,
                             discard the un-iterated `inner_generator`.
      • Cache hit + stale  → emit cached payload immediately, kick off a
                             background task to drain `inner_generator` and
                             refresh the cache for the next visitor.
      • Cache miss / force → drive `inner_generator`, capture the final
                             `result` event, write to cache.

    `inner_generator` MUST be a freshly-created async generator (not yet
    iterated). On a cache hit we either discard it or hand it off to a
    background task.
    """
    if not force_refresh:
        cached, _ = response_cache.get(cache_key, max_ttl_s=max_ttl_s)
        if cached is not None:
            age = response_cache.age_seconds(cache_key) or 0
            label = (
                "Loaded from cache." if age < fresh_ttl_s
                else f"Loaded from cache ({int(age)}s old) — refreshing."
            )
            yield f"data: {json.dumps({'type':'step','message':label})}\n\n"
            yield f"data: {json.dumps(cached)}\n\n"
            yield "data: [DONE]\n\n"

            # If stale, background-refresh once. Multiple concurrent stale-hits
            # would otherwise kick off duplicate refreshes; the in-flight set
            # prevents that.
            if age >= fresh_ttl_s and cache_key not in response_cache._refreshing:
                response_cache._refreshing.add(cache_key)

                async def _bg_refresh():
                    try:
                        last = None
                        async for chunk in inner_generator:
                            if isinstance(chunk, str) and chunk.startswith("data: "):
                                body = chunk[6:].strip()
                                if body and body != "[DONE]":
                                    try:
                                        p = json.loads(body)
                                        if isinstance(p, dict) and p.get("type") == "result":
                                            last = p
                                    except (ValueError, json.JSONDecodeError):
                                        pass
                        if last:
                            response_cache.put(cache_key, last)
                    except Exception as e:
                        logger.warning("SSE bg refresh failed for %s: %s", cache_key, e)
                    finally:
                        response_cache._refreshing.discard(cache_key)

                try:
                    asyncio.create_task(_bg_refresh())
                except RuntimeError:
                    response_cache._refreshing.discard(cache_key)
            return

    # MISS / force_refresh — stream the inner generator, capturing the result
    # event for the cache so the next request is fast.
    last_result = None
    async for chunk in inner_generator:
        if isinstance(chunk, str) and chunk.startswith("data: "):
            body = chunk[6:].strip()
            if body and body != "[DONE]":
                try:
                    p = json.loads(body)
                    if isinstance(p, dict) and p.get("type") == "result":
                        last_result = p
                except (ValueError, json.JSONDecodeError):
                    pass
        yield chunk

    if last_result is not None:
        response_cache.put(cache_key, last_result)


async def _intelligence_generator(raw_holdings: list[dict]):
    # Step messages are shorter + more honest now. Old list included "Verifying
    # claims against portfolio data..." which is gone — the verifier pass was
    # removed to save 10-20s per analysis (OpenAI JSON mode + grounded prompt
    # produces strict-schema output; verifier rarely caught real hallucinations).
    for msg in [
        "Fetching live prices for each holding...",
        "Computing P&L, sector allocation, peer benchmarks...",
        "Running grounded AI strategist...",
    ]:
        yield f"data: {json.dumps({'type':'step','message':msg})}\n\n"
        await asyncio.sleep(0.25)

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'step','message':'ERROR: AI client not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        # Hard wall: context build can call yfinance for 40+ holdings; yf_safe
        # now bounds each call, but stacking them still warrants a safety net.
        context = await asyncio.wait_for(
            asyncio.to_thread(grounding.build_portfolio_context, raw_holdings),
            timeout=60,
        )
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'type':'error','message':'Market data is slow right now — please retry.'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'type':'error','message':f'Context build failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # PROMPT TIGHTENING (May 2026) — was producing vague generic output like
    # "consider diversifying" / "monitor closely". The new prompt:
    #   • bans the specific phrases users flagged as low-signal
    #   • forces every reason to cite a concrete CONTEXT number
    #   • adds 1 good/bad few-shot pair so the model has a calibration anchor
    # Goal: every line a user reads should contain a number or a ticker.
    task = (
        "You are a portfolio analyst writing for an Indian retail investor. "
        "Be specific, be brief, and ground every claim in a number that "
        "already appears in CONTEXT.\n\n"
        "THIS RUN PRODUCES TWO TIERS:\n"
        "  TIER 1 — portfolio-level: health score + breakdown + risks + directions\n"
        "  TIER 2 — `holding_theses`: rich per-position cards on the top 6 holdings "
        "    by weight_pct OR |unrealized_pnl_pct|. Each card is a decision aid, "
        "    not a label. See HOLDING-CARD RULES below.\n\n"
        "HOLDING-CARD RULES (the meat of this output):\n"
        "  For each of the top 6 holdings, produce a thesis card with:\n"
        "    • thesis      — ONE sentence on WHY people own this name (e.g. "
        "      'Largest Indian IT services exporter; USD revenue + buyback yield.'). "
        "      Universal — independent of today's price.\n"
        "    • bull_case   — 2-3 concrete reasons SUPPORTING the position. Each "
        "      bullet must cite a number from CONTEXT (ROE, margin, growth%, "
        "      PE vs sector, momentum_20d_pct, peer_percentile, FII flow, "
        "      relevant macro headline). One sentence each, ≤ 120 chars.\n"
        "    • bear_case   — 2-3 concrete reasons AGAINST. Same grounding rules. "
        "      Even bullish names must have a bear case — markets are 2-sided.\n"
        "    • watch       — 1-2 specific catalysts with TRIGGER CONDITIONS in "
        "      'if X then Y' format (e.g. 'Earnings 14 May; if margin guide < "
        "      21% the IT-services rerating thesis weakens'). Cite "
        "      upcoming_earnings or news/sem items if present.\n"
        "    • signal      — BULLISH / NEUTRAL / CAUTIOUS\n"
        "    • conviction  — 0-100. Below 60 means the bull and bear cases are "
        "      closely matched; above 80 means one side overwhelmingly dominates.\n\n"
        "GROUNDING RULES (apply to ALL text in this response):\n"
        "  • `source` fields reference the CONTEXT path (e.g. "
        "    'holdings[INFY].snapshot.roe_pct' or 'aggregate.top_sector_pct').\n"
        "  • Risks must cite CONTEXT.aggregate (top_holding_pct, top_sector_pct, "
        "    sector_allocation, concentration_flag) with the SPECIFIC % number.\n"
        "  • Do NOT mention tickers outside CONTEXT.holdings — directions are "
        "    sector- or factor-level only.\n\n"
        "BANNED PHRASES — these say nothing. Do not use:\n"
        "  • 'consider diversifying' (say WHICH sector is overweight + by how much)\n"
        "  • 'monitor closely' (say WHAT to monitor — earnings date, RSI, etc.)\n"
        "  • 'depends on market conditions' (no information content)\n"
        "  • 'may impact' / 'could affect' (use 'if X then Y' framing instead)\n"
        "  • 'strong fundamentals' (cite the actual ROE or margin number)\n"
        "  • 'high growth potential' (cite revenue_growth_pct or earnings_growth_pct)\n\n"
        "COMPLIANCE: `signal` is BULLISH/NEUTRAL/CAUTIOUS only — never buy/sell/hold. "
        "We are unregistered (not a SEBI RA), so output is educational assessment, "
        "not advice.\n\n"
        "OUTPUT BUDGET:\n"
        "  • holding_theses: EXACTLY 6 cards (top 6 by weight or |pnl_pct|)\n"
        "  • holdings_verdicts: top 20 one-liners (for the sortable table)\n"
        "  • top_risks: exactly 4, ranked by severity\n"
        "  • suggested_directions: exactly 3 sector/factor-level focuses\n\n"
        "EXAMPLES — good vs bad bullets:\n"
        "  BAD:   'Strong fundamentals support a bullish stance.'\n"
        "  GOOD:  'ROE 31% + rev growth 13% beat sector median; trades at 1.2× peer PE.'\n"
        "  BAD:   'Consider monitoring this position.'\n"
        "  GOOD:  'Weight 18% — above your 15% concentration band; PE 42 vs sector 24.'\n"
        "  BAD:   'Earnings season approaching.'\n"
        "  GOOD:  'Earnings 14 May (3 days); if margin guide < 21% the rerating thesis flips.'"
    )
    schema = """{
  "portfolio_health_score": int (1-100) | null,
  "health_breakdown": {
    "diversification": int (1-100) | null,
    "quality": int (1-100) | null,
    "risk": int (1-100) | null,
    "momentum": int (1-100) | null
  },
  "holding_theses": [
    {
      "ticker": str,
      "thesis": str,
      "bull_case": [ { "text": str, "source": str } ],
      "bear_case": [ { "text": str, "source": str } ],
      "watch":     [ { "text": str, "source": str } ],
      "signal": "BULLISH" | "NEUTRAL" | "CAUTIOUS",
      "conviction": int (0-100)
    }
  ],
  "holdings_verdicts": [
    { "ticker": str,
      "signal": "BULLISH" | "NEUTRAL" | "CAUTIOUS",
      "reason": { "text": str, "source": str },
      "confidence": int (1-100) }
  ],
  "top_risks": [ { "title": str, "description": { "text": str, "source": str } } ],
  "suggested_directions": [
    { "focus": str,               // e.g. "Defensive large-cap IT"
      "rationale": { "text": str, "source": str },
      "conviction": "HIGH" | "MEDIUM" }
  ],
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    # Heartbeat-wrapped LLM call — same pattern as /movers. Sends a step every
    # 15s so Render's edge proxy doesn't close the SSE connection during the
    # 30-90s LLM phase, and so the UI doesn't sit on "Running grounded AI
    # strategist..." for a minute straight.
    # 6500 tokens — holding_theses are rich (6 cards × ~5 bullets + watch +
    # thesis line ≈ 2.5K tokens) plus the existing tier-1 output (~2K) plus
    # JSON-mode overhead. 6500 keeps headroom for verbose ticker names + the
    # data_gaps tail without truncating mid-array.
    llm_task = asyncio.ensure_future(
        asyncio.to_thread(ai_client.generate_grounded_json, task, context, schema, 6500)
    )
    heartbeat_msgs = [
        "Scoring portfolio health across 4 axes...",
        "Building bull + bear cases for top holdings...",
        "Identifying catalysts and watch triggers...",
        "Surfacing concentration + sector risks...",
        "Still working — rich theses take a bit longer...",
        "Almost there — finalizing rebalance directions...",
    ]
    hb_idx = 0
    # Bumped to 150s — richer holding_theses output (~2.5K extra tokens) means
    # the LLM call runs noticeably longer than the old "verdicts only" path.
    # On Render the round-trip is 2-3× local; 150s prevents premature retries.
    deadline = asyncio.get_event_loop().time() + 150
    try:
        while not llm_task.done():
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                llm_task.cancel()
                raise asyncio.TimeoutError
            try:
                await asyncio.wait_for(asyncio.shield(llm_task), timeout=min(15.0, remaining))
            except asyncio.TimeoutError:
                msg = heartbeat_msgs[hb_idx] if hb_idx < len(heartbeat_msgs) else "Still working..."
                hb_idx += 1
                yield f"data: {json.dumps({'type':'step','message':msg})}\n\n"
        data = llm_task.result()
    except asyncio.TimeoutError:
        if not llm_task.done():
            llm_task.cancel()
        yield f"data: {json.dumps({'type':'error','message':'AI Analysis timed out — please retry.'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        logger.exception("portfolio LLM call failed")
        yield f"data: {json.dumps({'type':'error','message':f'AI generation failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if not data:
        yield f"data: {json.dumps({'type':'error','message':'AI returned unparseable response.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Verifier pass intentionally removed — was a second 10-20s LLM round-trip
    # that rarely caught real hallucinations on grounded JSON-mode output. The
    # prompt's anti-vagueness rules + strict schema cover us. `verified` kept
    # as an empty dict so the downstream `removed_by_verifier` field still
    # serializes cleanly for any cached frontend code reading it.
    verified: dict = {"verified": data, "removed": []}
    data = verified["verified"]

    # Deterministic fallback for health breakdown — computed straight from the
    # grounding context (aggregate + holdings + technicals). The LLM's values
    # win when present; this fills any null sub-score so the AI Analysis bars
    # are never empty. Then the overall `portfolio_health_score` is the
    # weighted average — Diversification + Quality double-weighted (structural)
    # vs Risk + Momentum (conditions of the day).
    breakdown = dict(data.get("health_breakdown") or {})
    try:
        computed = grounding.compute_portfolio_health(context)
        for k, v in computed.items():
            if not isinstance(breakdown.get(k), (int, float)) and v is not None:
                breakdown[k] = v
    except Exception as e:
        logger.warning("compute_portfolio_health failed: %s", e)

    health_score = data.get("portfolio_health_score")
    if not isinstance(health_score, (int, float)) or health_score is None:
        weights = {"diversification": 2, "quality": 2, "risk": 1, "momentum": 1}
        num = den = 0
        for k, w in weights.items():
            v = breakdown.get(k)
            if isinstance(v, (int, float)):
                num += float(v) * w
                den += w
        if den > 0:
            health_score = round(num / den)

    # Hold the LLM accountable to its universe: drop any thesis card whose
    # ticker isn't in CONTEXT.holdings (hallucinated symbol = silently filter,
    # don't surface). Also cap to 6 in case the LLM over-produced.
    universe = {(h.get("ticker") or "").upper() for h in (context.get("holdings") or [])}
    raw_theses = data.get("holding_theses") or []
    holding_theses: list[dict] = []
    for t in raw_theses:
        tk = (t.get("ticker") or "").upper()
        if tk and tk in universe:
            holding_theses.append({**t, "ticker": tk})
        if len(holding_theses) >= 6:
            break

    result = with_disclaimer({
        "type": "result",
        "portfolio_health_score": health_score,
        "health_breakdown": breakdown,
        "holding_theses": holding_theses,
        "holdings_verdicts": data.get("holdings_verdicts", []),
        "top_risks": data.get("top_risks", []),
        "suggested_directions": data.get("suggested_directions", []),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
        "removed_by_verifier": verified.get("removed", []),
        "aggregate": context.get("aggregate", {}),
        "context_snapshot_at": context.get("generated_at"),
    })
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"

    # Same memory-hygiene pattern as the /movers path: drop request-scoped
    # context dicts before the next SSE call lands. Helps Render Starter
    # (512 MB) survive back-to-back analyses without tripping OOM.
    del context, data, verified
    gc.collect()


@router.post("/portfolio")
async def portfolio_intelligence(req: IntelRequest):
    if not req.positions:
        return {"error": "No holdings provided."}
    raw = [{"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price} for p in req.positions]
    # Cache key — keyed by the user's positions + today's date. Two users with
    # identical portfolios share the cache (same AI analysis applies to both).
    cache_key = response_cache.make_key(
        "intel-portfolio",
        sorted([(p["ticker"], round(p["quantity"], 2), round(p["buy_price"], 2)) for p in raw]),
        datetime.now(timezone.utc).date().isoformat(),
    )
    return StreamingResponse(
        _cached_sse_stream(_intelligence_generator(raw), cache_key, force_refresh=req.force_refresh),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Signal-ensemble post-processing — runs after the LLM, before serving.
# Selectivity > coverage: emit fewer, higher-conviction predictions. Items
# below the threshold are HIDDEN from the user-facing payload but still get
# logged to the outcome ledger so we can backtest "what if we'd kept them?"
# ---------------------------------------------------------------------------
def _apply_ensemble_to_per_holding(tomorrow_data: dict, movers_ctx: dict) -> int:
    """Mutates tomorrow_data["per_holding"] in place: overrides each item's
    `direction` with the ensemble consensus and adds `conviction` +
    `signal_breakdown`. Returns the count of items that fell below the
    user-facing conviction threshold (still in the list, marked
    `hidden_low_conviction=True`)."""
    items = (tomorrow_data or {}).get("per_holding") or []
    if not items:
        return 0

    holdings_by_ticker = {h.get("ticker"): h for h in (movers_ctx.get("holdings") or [])}
    sector_returns = {
        s.get("sector"): s.get("change_percent")
        for s in ((movers_ctx.get("market") or {}).get("sectors") or [])
    }
    flows = (movers_ctx.get("market") or {}).get("flows")

    hidden = 0
    for w in items:
        t = (w.get("ticker") or "").upper()
        h = holdings_by_ticker.get(t, {})
        tech = h.get("technicals")
        sector_chg = sector_returns.get(w.get("sector") or h.get("sector"))
        llm_dir = w.get("direction")

        ens = signal_ensemble.compute_ensemble(
            news_direction=llm_dir,
            technicals=tech,
            sector_change_pct=sector_chg,
            flows=flows,
        )
        # Preserve the LLM's original call so the modal can show "AI said X
        # but ensemble flipped to Y" — useful for investor-facing transparency.
        w["llm_direction"] = llm_dir
        w["direction"] = ens["consensus_direction"]
        w["conviction"] = ens["conviction"]
        w["signal_breakdown"] = ens["breakdown"]
        w["agreeing_signals"] = ens["agreeing_signals"]
        w["conflicting_signals"] = ens["conflicting_signals"]
        if ens["conviction"] < signal_ensemble.MIN_CONVICTION_FOR_USER:
            w["hidden_low_conviction"] = True
            hidden += 1
    return hidden


def _apply_ensemble_to_news_items(
    cleaned_items: list[dict],
    tech_by_ticker: dict,
    sector_returns_today: list[dict] | None,
    flows: dict | None,
) -> int:
    """Same idea for News Impact items. Mutates each item with `conviction`,
    `signal_breakdown`, `hidden_low_conviction`. Returns hidden count.

    For news items the affected ticker's technicals come from `tech_by_ticker`
    (universe technicals already computed in news_feed). The "primary" affected
    ticker (first in the list) drives the ensemble — secondary tickers just
    inherit the same conviction so the row stays coherent.
    """
    if not cleaned_items:
        return 0

    sector_map = {
        s.get("sector"): s.get("change_percent")
        for s in (sector_returns_today or [])
    }

    hidden = 0
    for it in cleaned_items:
        affected = it.get("affected_tickers") or []
        primary = affected[0].upper() if affected else None
        tech = tech_by_ticker.get(primary) if primary else None
        # Sector change isn't reliably attached to news items; skip if absent.
        # The ensemble degrades gracefully when a signal is None.
        sector_chg = None  # we don't carry per-item sector mapping for news_feed
        llm_dir = it.get("direction")

        ens = signal_ensemble.compute_ensemble(
            news_direction=llm_dir,
            technicals=tech,
            sector_change_pct=sector_chg,
            flows=flows,
        )
        it["llm_direction"] = llm_dir
        it["direction"] = ens["consensus_direction"]
        it["conviction"] = ens["conviction"]
        it["signal_breakdown"] = ens["breakdown"]
        it["agreeing_signals"] = ens["agreeing_signals"]
        it["conflicting_signals"] = ens["conflicting_signals"]
        if ens["conviction"] < signal_ensemble.MIN_CONVICTION_FOR_USER:
            it["hidden_low_conviction"] = True
            hidden += 1
    return hidden


# ---------------------------------------------------------------------------
# Outcome-ledger helpers — log forward-looking AI calls so /accuracy can grade
# them later. Both helpers are best-effort: any failure is swallowed by the
# fire-and-forget task that calls them.
# ---------------------------------------------------------------------------
def _log_tomorrow_predictions(tomorrow_data: dict, movers_ctx: dict) -> None:
    """Persist Tomorrow per_holding watch items as forward-looking predictions.

    Each row is dedup-keyed `tomorrow:{ticker}:{date}` so re-running the Context
    Engine the same day replaces the latest call instead of accumulating dupes.
    """
    items = (tomorrow_data or {}).get("per_holding") or []
    if not items:
        return
    today_iso = datetime.now(timezone.utc).date().isoformat()
    holdings_by_ticker = {h.get("ticker"): h for h in (movers_ctx.get("holdings") or [])}

    rows: list[dict] = []
    for w in items:
        t = (w.get("ticker") or "").upper()
        if not t:
            continue
        h = holdings_by_ticker.get(t, {})
        tech = h.get("technicals") or {}
        slim_tech = {
            k: tech.get(k) for k in (
                "rsi14", "rsi_zone", "vol_vs_avg20", "vol_zone",
                "momentum_5d_pct", "momentum_20d_pct", "momentum_state",
                "sma_state",
            ) if tech.get(k) is not None
        } or None
        rows.append({
            "ticker": t,
            "prediction_date": today_iso,
            "source": "tomorrow_per_holding",
            "direction": w.get("direction") or "neutral",
            "impact_level": w.get("importance"),
            "catalyst_type": w.get("catalyst_type"),
            "reason": w.get("what_to_watch"),
            "cited_sources": w.get("sources") or [],
            "technical_state": slim_tech,
            "price_at_call": h.get("current_price"),
            "dedup_key": f"tomorrow:{t}:{today_iso}",
            "metadata": {"sector": w.get("sector")},
        })
    if rows:
        outcome_ledger.log_predictions(rows)


def _log_news_feed_predictions(cleaned_items: list[dict], tech_by_ticker: dict) -> None:
    """Persist annotated News Impact items as predictions — one row per
    (item × affected_ticker). Skip 'mixed' direction (not scoreable). Dedup key
    `news_feed:{ticker}:{news_id}:{date}` so concurrent users hitting the
    same endpoint replace instead of duplicate.
    """
    if not cleaned_items:
        return
    today_iso = datetime.now(timezone.utc).date().isoformat()
    rows: list[dict] = []
    for it in cleaned_items:
        direction = it.get("direction")
        if not direction or direction == "mixed":
            continue
        news_id = it.get("news_id") or ""
        for t in (it.get("affected_tickers") or []):
            tkr = t.upper()
            rows.append({
                "ticker": tkr,
                "prediction_date": today_iso,
                "source": "news_feed",
                "direction": direction,
                "impact_level": it.get("impact_level"),
                "catalyst_type": it.get("category"),
                "reason": it.get("reason"),
                "cited_sources": [news_id] if news_id else [],
                "technical_state": tech_by_ticker.get(tkr),
                # price_at_call left None — compute_pending_outcomes falls back
                # to the price history's anchor close. Cheaper than fetching
                # snapshots inline for every news item.
                "price_at_call": None,
                "dedup_key": f"news_feed:{tkr}:{news_id}:{today_iso}",
                "metadata": {
                    "headline": (it.get("headline") or "")[:240] or None,
                    "semantic_match_ticker": it.get("semantic_match_ticker"),
                    "semantic_similarity": it.get("semantic_similarity"),
                },
            })
    if rows:
        outcome_ledger.log_predictions(rows)


# ---------------------------------------------------------------------------
# Context Engine — Why did my portfolio move today / What to watch tomorrow
# ---------------------------------------------------------------------------
async def _movers_generator(raw_holdings: list[dict]):
    for msg in [
        "Fetching NIFTY + sector index returns...",
        "Pulling today's headlines from India...",
        "Pulling overnight headlines from US / CN / EU / JP...",
        "Computing per-holding excess returns vs sector...",
        "Attributing today's moves to catalysts...",
        "Scanning for tomorrow's catalysts...",
    ]:
        yield f"data: {json.dumps({'type':'step','message':msg})}\n\n"
        await asyncio.sleep(0.25)

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'error','message':'AI client not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        # Hard ceiling: every blocking dep (yfinance, RSS, RBI/PIB feeds, pgvector)
        # now has its own timeout, but stacking 41 holdings × 4 calls means we
        # still want a wall-clock safety net so a partial network brown-out
        # surfaces as a clean error instead of a frozen browser tab.
        market_ctx = await asyncio.wait_for(
            asyncio.to_thread(grounding.build_market_context),
            timeout=45,
        )
        movers_ctx = await asyncio.wait_for(
            asyncio.to_thread(grounding.build_movers_context, raw_holdings, market_ctx),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.warning("movers context build exceeded ceiling")
        yield f"data: {json.dumps({'type':'error','message':'Market data is slow right now — please retry.'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        logger.exception("movers context build failed")
        yield f"data: {json.dumps({'type':'error','message':f'Context build failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # -------- Today attribution --------
    today_task = (
        "For each holding in CONTEXT.holdings whose mover_bucket is 'strong_gainer' or "
        "'strong_loser', explain today's price move using EVERY available signal:\n"
        "  1. PRIMARY DRIVER — one of:\n"
        "     • 'stock_specific'  — cite a {TICKER}_news[i] OR a {TICKER}_sem[i] (semantic match: "
        "       the headline may not name the ticker but pgvector matched it on theme — perfectly "
        "       valid; cite the semantic id and similarity).\n"
        "     • 'sector'          — cite CONTEXT.market.sectors[i] + the sign of excess_return_today.\n"
        "     • 'macro'           — cite CONTEXT.india_headlines[i] or CONTEXT.market.indices.\n"
        "     • 'flow'            — cite CONTEXT.market.flows (FII/DII) when the move aligns with the day's flow direction.\n"
        "     • 'technical'       — when there is NO news but technicals explain the move "
        "       (e.g. RSI oversold bounce, breakout above SMA50 with volume surge, breakdown "
        "       through 20d low on heavy volume). Cite the holding's technicals fields.\n"
        "     • 'unexplained'     — ONLY if news, semantic_news, sector, macro, flow, and technicals "
        "       all fail. Add a specific data_gaps entry naming what was missing.\n"
        "  2. TECHNICAL CONFIRMATION — for every mover, fill technical_state with:\n"
        "       rsi_zone, vol_zone, momentum_state, sma_state — copied/derived from "
        "       CONTEXT.holdings[].technicals. Add a one-line confirms_or_contradicts note "
        "       (e.g. 'volume surge + extending_up confirms the move' or 'rally on weak volume — "
        "       move may not stick').\n"
        "  3. ATTRIBUTION — 1-3 items per holding, each with text + source + weight_pct (1-100).\n"
        "Be specific. 'Positive price movement enhances sentiment' is BANNED — it says nothing.\n"
        "Use concrete language: 'crude +3% (sem similarity 0.71) → ONGC realisations boost', "
        "'sector index +2.1% on PSB earnings beat → BANKBARODA rides the wave on 1.4x avg vol'."
    )
    today_schema = """{
  "portfolio_return_today_pct": float | null,
  "top_positive_driver": { "text": str, "source": str } | null,
  "top_negative_driver": { "text": str, "source": str } | null,
  "movers": [
    {
      "ticker": str,
      "move_percent": float,
      "primary_driver": "stock_specific" | "sector" | "macro" | "flow" | "technical" | "unexplained",
      "attribution": [ { "text": str, "source": str, "weight_pct": int } ],
      "technical_state": {
        "rsi_zone": "oversold" | "weak" | "neutral" | "strong" | "overbought" | null,
        "vol_zone": "low" | "normal" | "high" | "surge" | null,
        "momentum_state": str | null,
        "sma_state": "above_sma50" | "below_sma50" | null,
        "confirms_or_contradicts": str
      }
    }
  ],
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    # Slim today CONTEXT: only actual movers, drop snippets, drop flat holdings.
    # Groq free tier is 12K TPM — full movers_ctx blows past that.
    def _slim_news(items, limit=2):
        return [
            {"id": n.get("id"), "source": n.get("source"), "headline": n.get("headline")}
            for n in (items or [])[:limit]
        ]

    def _slim_sem(items, limit=3):
        return [
            {
                "id": n.get("id"),
                "source": n.get("source"),
                "headline": n.get("headline"),
                "similarity": n.get("similarity"),
            }
            for n in (items or [])[:limit]
        ]

    def _slim_tech(tech):
        # Drop nulls so the LLM sees a tight payload.
        if not tech:
            return None
        keep = (
            "rsi14", "rsi_zone", "vol_vs_avg20", "vol_zone",
            "momentum_5d_pct", "momentum_20d_pct", "momentum_state",
            "sma_state", "pct_from_20d_high",
        )
        return {k: tech.get(k) for k in keep if tech.get(k) is not None}

    # Cap at the top 10 movers by absolute change — keeps the prompt + output
    # bounded regardless of portfolio size. Cuts LLM completion time 30-40%
    # on 40+ holding portfolios. The 11th-onward mover rarely tells the user
    # something the top 10 didn't already.
    _eligible = [
        h for h in movers_ctx.get("holdings", [])
        if h.get("mover_bucket") in ("strong_gainer", "strong_loser")
    ]
    _eligible.sort(key=lambda h: abs(h.get("change_percent_today") or 0), reverse=True)
    _eligible = _eligible[:10]
    mover_holdings = [
        {
            "ticker": h["ticker"],
            "sector": h.get("sector"),
            "change_percent_today": h.get("change_percent_today"),
            "sector_index_return_today": h.get("sector_index_return_today"),
            "excess_return_today": h.get("excess_return_today"),
            "mover_bucket": h.get("mover_bucket"),
            "news": _slim_news(h.get("news"), limit=1),         # was 2
            "semantic_news": _slim_sem(h.get("semantic_news"), limit=2),
            "technicals": _slim_tech(h.get("technicals")),
        }
        for h in _eligible
    ]

    today_input = {
        "portfolio_return_today_pct": movers_ctx.get("portfolio_return_today_pct"),
        "holdings": mover_holdings,
        "market": {
            "sectors": [
                {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
                for s in movers_ctx.get("market", {}).get("sectors", [])
            ],
            "flows": movers_ctx.get("market", {}).get("flows"),
        },
        "india_headlines": _slim_news(market_ctx.get("india_headlines"), limit=4),
    }

    # -------- Tomorrow outlook --------
    tomorrow_task = (
        "Produce a SPECIFIC, HOLDING-CENTRIC outlook for tomorrow — not generic macro headlines. "
        "Use every signal in CONTEXT.holdings (semantic_news, technicals, upcoming_earnings) plus "
        "global_headlines + india_headlines + market.flows (FII/DII).\n\n"
        "OUTPUT TWO LAYERS:\n"
        "  A) per_holding[] — for EACH holding in CONTEXT.holdings that has at least ONE of: "
        "     an upcoming_earnings entry, a semantic_news match with similarity ≥ 0.6, OR a "
        "     stretched technical state (rsi_zone overbought/oversold, vol_zone surge, "
        "     momentum_state extending_*, or pct_from_20d_high within ±2%). "
        "     Build a 'watch_item' object with:\n"
        "       - ticker, sector\n"
        "       - catalyst_type: 'earnings' | 'news' | 'technical' | 'sector_flow' | 'mixed'\n"
        "       - what_to_watch: ONE concrete sentence — e.g. 'Earnings on 2026-05-15 (3 days); "
        "         consensus expects margin expansion; technicals show momentum_state extending_up with "
        "         vol 1.4x avg — beat could push to 20d high.'\n"
        "       - direction: 'positive' | 'negative' | 'mixed' | 'neutral'\n"
        "       - importance: 'high' | 'medium' | 'low'\n"
        "       - sources: list of ids from {TICKER}_news[i] / {TICKER}_sem[i] / 'technicals' / 'upcoming_earnings'\n"
        "  B) macro_themes[] — 1-3 cross-cutting macro themes from global/india headlines that may "
        "     touch MULTIPLE holdings (e.g. crude spike, Fed decision, FII outflow). Each theme must "
        "     list the affected_holdings explicitly — no theme allowed without naming holdings.\n\n"
        "RULES:\n"
        "  • At least 60% of output items must be per_holding[], NOT macro_themes[]. The user wants "
        "    'what about MY stocks tomorrow', not 'general market commentary'.\n"
        "  • If FII/DII flows in CONTEXT.market.flows are large (|net_inr_cr| > 1000), surface that "
        "    in a macro_theme with the specific number cited.\n"
        "  • If a holding has NO catalyst, do NOT include it. Empty watchlist is fine.\n"
        "  • NEVER use phrases like 'may impact', 'could affect', 'foreign investors exiting' without a number. "
        "    Be specific: 'crude headline +X% on global_news[i] → ONGC realisations positive' beats "
        "    'rising crude prices'.\n"
        "\n"
        "DIRECTION DISCIPLINE — read carefully:\n"
        "  • DEFAULT TO 'neutral' when in doubt. Markets are noisy; over-confident calls are how AI "
        "    products lose credibility. Use 'positive' / 'negative' ONLY when the evidence in CONTEXT "
        "    strongly supports it (e.g. a clear earnings beat catalyst with confirming technicals, OR "
        "    a sector index move > 1.5% with named affected stocks).\n"
        "  • If technicals contradict the news catalyst (e.g. positive earnings but the stock is "
        "    extending_down with vol surge — institutions selling into the print), call it 'mixed' or "
        "    'neutral'. Do NOT force a direction just because there's a catalyst.\n"
        "  • BANNED words/phrases: 'will likely', 'expected to', 'should rise', 'poised to'. These are "
        "    forecasts dressed as facts. Use 'if X then Y' framing instead — 'if the print beats, the "
        "    setup supports a bounce; if it misses, momentum_state extending_down extends'."
    )
    tomorrow_schema = """{
  "per_holding": [
    {
      "ticker": str,
      "sector": str,
      "catalyst_type": "earnings" | "news" | "technical" | "sector_flow" | "mixed",
      "what_to_watch": str,
      "direction": "positive" | "negative" | "mixed" | "neutral",
      "importance": "high" | "medium" | "low",
      "sources": [ str ]
    }
  ],
  "macro_themes": [
    {
      "theme": str,
      "direction": "positive" | "negative" | "mixed",
      "affected_holdings": [ str ],
      "affected_sectors": [ str ],
      "mechanism": { "text": str, "source": str },
      "importance": "high" | "medium" | "low"
    }
  ],
  "overall_bias": "positive" | "negative" | "neutral",
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    # Slim tomorrow CONTEXT: cap global to 1/country, drop snippets everywhere.
    # Tomorrow's LLM call doesn't need rich news context — it works mostly
    # off per_holding catalysts + a couple of macro headlines.
    slim_global = []
    per_country: dict[str, int] = {}
    for n in market_ctx.get("global_headlines", []):
        c = n.get("country") or "?"
        if per_country.get(c, 0) >= 1:    # was 2
            continue
        per_country[c] = per_country.get(c, 0) + 1
        slim_global.append({
            "id": n.get("id"),
            "country": c,
            "source": n.get("source"),
            "headline": n.get("headline"),
        })

    # For tomorrow we want per-holding catalysts so the LLM can produce
    # specific watch items instead of generic macro themes. Filter to holdings
    # that actually have a catalyst to keep token spend reasonable.
    def _has_catalyst(h: dict) -> bool:
        if h.get("upcoming_earnings"):
            return True
        sem = h.get("semantic_news") or []
        if any((s.get("similarity") or 0) >= 0.6 for s in sem):
            return True
        tech = h.get("technicals") or {}
        if tech.get("rsi_zone") in ("overbought", "oversold"):
            return True
        if tech.get("vol_zone") == "surge":
            return True
        if tech.get("momentum_state") in ("extending_up", "extending_down"):
            return True
        p20h = tech.get("pct_from_20d_high")
        if p20h is not None and abs(p20h) <= 2.0:
            return True
        return False

    # Cap at 15 holdings into the LLM (sorted by catalyst strength) so the
    # prompt size and output size both stay bounded. The ensemble filter
    # downstream typically drops half anyway — feeding the LLM the strongest
    # 15 catalysts is enough to surface the high-conviction calls.
    _catalyst_candidates = [h for h in movers_ctx.get("holdings", []) if _has_catalyst(h)]

    def _catalyst_strength(h: dict) -> int:
        # Earnings within 7 days = strongest; semantic match similarity adds;
        # stretched technicals add. Used only to rank input to the LLM.
        score = 0
        e = h.get("upcoming_earnings") or {}
        if e and (e.get("days_ahead") or 99) <= 7:
            score += 10
        elif e:
            score += 5
        sem = h.get("semantic_news") or []
        score += max((round((s.get("similarity") or 0) * 10) for s in sem), default=0)
        tech = h.get("technicals") or {}
        if tech.get("rsi_zone") in ("overbought", "oversold"): score += 3
        if tech.get("vol_zone") == "surge": score += 3
        if tech.get("momentum_state") in ("extending_up", "extending_down"): score += 2
        return score

    _catalyst_candidates.sort(key=_catalyst_strength, reverse=True)
    tomorrow_holdings: list[dict] = []
    for h in _catalyst_candidates[:15]:
        tomorrow_holdings.append({
            "ticker": h["ticker"],
            "sector": h.get("sector"),
            "upcoming_earnings": h.get("upcoming_earnings"),
            "semantic_news": _slim_sem(h.get("semantic_news"), limit=2),
            "technicals": _slim_tech(h.get("technicals")),
            "change_percent_today": h.get("change_percent_today"),
        })

    tomorrow_input = {
        "holdings": tomorrow_holdings,
        "all_holding_tickers": [h["ticker"] for h in movers_ctx.get("holdings", [])],
        "sector_allocation_today": [
            {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
            for s in movers_ctx.get("market", {}).get("sectors", [])
        ],
        "india_headlines": _slim_news(market_ctx.get("india_headlines"), limit=5),
        "global_headlines": slim_global,
        "market_flows": movers_ctx.get("market", {}).get("flows"),
    }

    # Short-circuit today call if nothing moved enough to attribute.
    async def _run_today():
        if not mover_holdings:
            return {"movers": [], "confidence": "high",
                    "data_gaps": ["No holding moved ≥1.5% today."]}
        return await asyncio.to_thread(
            # 2200 tokens: covers ≤10 movers with technical_state + 1-2 attributions.
            ai_client.generate_grounded_json, today_task, today_input, today_schema, 2200
        )

    # Heartbeat: emit progress messages while the LLMs grind so the SSE
    # connection has bytes flowing (Render's proxy closes idle streams) and
    # so the UI doesn't look frozen on the last step for a minute straight.
    # asyncio.gather() already returns a Future — wrapping it in create_task()
    # was a bug (create_task needs a coroutine). The gather Future supports
    # .done() / .result() / .cancel() / asyncio.shield natively.
    llm_task = asyncio.gather(
        _run_today(),
        # 2200 tokens: ≤15 holdings × per_holding watch item + 1-3 macro themes.
        asyncio.to_thread(ai_client.generate_grounded_json, tomorrow_task, tomorrow_input, tomorrow_schema, 2200),
    )
    heartbeat_msgs = [
        "Cross-checking holdings against today's news + technicals...",
        "Ranking catalysts by conviction (multi-signal ensemble)...",
        "Still working — large portfolios take a bit longer...",
        "Almost there — finalizing tomorrow's watch list...",
    ]
    hb_idx = 0
    deadline = asyncio.get_event_loop().time() + 130
    try:
        while not llm_task.done():
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                llm_task.cancel()
                raise asyncio.TimeoutError
            try:
                await asyncio.wait_for(asyncio.shield(llm_task), timeout=min(15.0, remaining))
            except asyncio.TimeoutError:
                # 15s tick without completion — send a heartbeat step + loop.
                if hb_idx < len(heartbeat_msgs):
                    msg = heartbeat_msgs[hb_idx]
                    hb_idx += 1
                else:
                    msg = "Still working..."
                yield f"data: {json.dumps({'type':'step','message':msg})}\n\n"
        today_data, tomorrow_data = llm_task.result()
    except asyncio.TimeoutError:
        if not llm_task.done():
            llm_task.cancel()
        yield f"data: {json.dumps({'type':'error','message':'Context Engine timed out — please retry.'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        logger.exception("movers LLM call failed")
        yield f"data: {json.dumps({'type':'error','message':f'AI generation failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    today_data = today_data or {}
    tomorrow_data = tomorrow_data or {}

    # Multi-signal ensemble — override each per_holding item's direction with
    # the consensus of news + technicals + sector + flow. Adds `conviction`
    # (0-95) so the UI can show honest uncertainty. Items below the threshold
    # are MARKED hidden but stay in the array so the ledger logs them too —
    # we want to backtest "what would these have looked like if we'd kept them?"
    hidden_tomorrow_count = _apply_ensemble_to_per_holding(tomorrow_data, movers_ctx)

    # Outcome ledger — log every Tomorrow per_holding item (incl. hidden ones)
    # as a forward-looking prediction. Synchronous (in a thread) so we don't
    # hand off to a fire-and-forget task that may get garbage-collected as the
    # SSE generator winds down. ~100ms cost added on top of the 30s+ LLM call.
    # Today's attribution is intentionally NOT logged — it's an *explanation*
    # of a move that already happened, not a forecast.
    if outcome_ledger.is_available():
        try:
            await asyncio.to_thread(
                _log_tomorrow_predictions, tomorrow_data, movers_ctx,
            )
        except Exception as e:
            logger.warning("outcome_ledger logging failed: %s", e)

    # Verifier intentionally NOT run on movers output. It cost 10-15s
    # end-to-end and added little value here: the today_data already comes out
    # of OpenAI's JSON mode with strict schema and every claim cites a source
    # id from CONTEXT. Risk of hallucinated unsupported claims is low. The
    # /portfolio (AI Analysis) endpoint still uses the verifier where it matters.

    # Per-ticker raw evidence for click-through detail modals. Keyed by ticker
    # so the frontend can show the full reasoning chain (cited sources, raw
    # RSI/vol numbers, every semantic match w/ similarity) without a second
    # round-trip. We forward ALL holdings — Today's modals use the movers and
    # Tomorrow's modals reference any holding flagged as a watch item.
    holdings_detail: dict[str, dict] = {}
    for h in movers_ctx.get("holdings", []):
        t = h.get("ticker")
        if not t:
            continue
        holdings_detail[t] = {
            "name": h.get("name"),
            "sector": h.get("sector"),
            "change_percent_today": h.get("change_percent_today"),
            "sector_index_return_today": h.get("sector_index_return_today"),
            "excess_return_today": h.get("excess_return_today"),
            "news": h.get("news") or [],
            "semantic_news": h.get("semantic_news") or [],
            "technicals": h.get("technicals"),
            "upcoming_earnings": h.get("upcoming_earnings"),
        }

    # Per-user live snapshot (qty × current price → ₹ stake + day P&L per ticker)
    # so the frontend can render the "Contributed today" / "Your stake" strip
    # on every mover, watch item, and theme. Cheap — quotes are 5-min cached.
    holdings_today = _build_holdings_today(raw_holdings)

    result = with_disclaimer({
        "type": "result",
        "portfolio_return_today_pct": movers_ctx.get("portfolio_return_today_pct"),
        "market_indices": movers_ctx.get("market", {}).get("indices", {}),
        "sector_returns": movers_ctx.get("market", {}).get("sectors", []),
        "market_flows": movers_ctx.get("market", {}).get("flows"),
        "holdings_detail": holdings_detail,
        "holdings_today": holdings_today,
        "today": {
            "top_positive_driver": today_data.get("top_positive_driver"),
            "top_negative_driver": today_data.get("top_negative_driver"),
            "movers": today_data.get("movers", []),
            "confidence": today_data.get("confidence", "low"),
            "data_gaps": today_data.get("data_gaps", []),
        },
        "tomorrow": {
            # Only emit items that cleared the conviction threshold (multi-signal
            # ensemble agreed). All items including hidden ones are logged to the
            # ledger above so the /accuracy page can backtest both kept + dropped.
            "per_holding": [w for w in tomorrow_data.get("per_holding", []) if not w.get("hidden_low_conviction")],
            "hidden_low_conviction_count": hidden_tomorrow_count,
            "min_conviction": signal_ensemble.MIN_CONVICTION_FOR_USER,
            "macro_themes": tomorrow_data.get("macro_themes", []),
            "themes": tomorrow_data.get("macro_themes", []) or tomorrow_data.get("themes", []),
            "overall_bias": tomorrow_data.get("overall_bias", "neutral"),
            "confidence": tomorrow_data.get("confidence", "low"),
            "data_gaps": tomorrow_data.get("data_gaps", []),
        },
        "context_snapshot_at": movers_ctx.get("generated_at"),
    })
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"

    # Free the large per-request DataFrames + LLM-response dicts before the
    # next SSE request lands. Render Starter is 512 MB; without this, idle
    # pandas memory from yfinance.history() calls accumulates across requests
    # and trips the OOM killer after a few back-to-back runs.
    del movers_ctx, market_ctx, today_data, tomorrow_data, today_input, tomorrow_input
    del mover_holdings, tomorrow_holdings, holdings_detail, holdings_today
    gc.collect()


@router.post("/movers")
async def portfolio_movers(req: MoversRequest):
    if not req.positions:
        return {"error": "No holdings provided."}
    raw = [{"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price} for p in req.positions]
    cache_key = response_cache.make_key(
        "intel-movers",
        sorted([(p["ticker"], round(p["quantity"], 2), round(p["buy_price"], 2)) for p in raw]),
        datetime.now(timezone.utc).date().isoformat(),
    )
    return StreamingResponse(
        _cached_sse_stream(_movers_generator(raw), cache_key, force_refresh=req.force_refresh),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Morning Brief — personalized "what matters for YOUR portfolio today"
# ---------------------------------------------------------------------------
from cachetools import TTLCache
from datetime import datetime, timezone

# Cached for 4 hours, keyed by content (date + holdings tickers + watchlist tickers).
# Two users with identical universes share the cached brief — saves AI cost dramatically.
_morning_brief_cache: TTLCache = TTLCache(maxsize=200, ttl=4 * 60 * 60)

# Sample portfolio used when a user has no holdings + empty watchlist (cold start).
# Lets the startup demo viewer see the value in <2 seconds without needing data.
_DEMO_HOLDINGS = [
    {"ticker": "INFY", "quantity": 10, "buy_price": 1500},
    {"ticker": "TCS",  "quantity": 5,  "buy_price": 3500},
    {"ticker": "RELIANCE", "quantity": 8,  "buy_price": 2400},
    {"ticker": "HDFCBANK", "quantity": 12, "buy_price": 1600},
    {"ticker": "TATAMOTORS", "quantity": 20, "buy_price": 600},
]
_DEMO_WATCHLIST = ["BAJFINANCE", "ITC", "ASIANPAINT"]


class MorningBriefRequest(BaseModel):
    positions: list[PositionIn] = []
    watchlist_tickers: list[str] = []
    force_refresh: bool = False  # bypass cache (used by frontend "Refresh" button)


def _brief_cache_key(positions: list[dict], watchlist: list[str]) -> str:
    # Date string makes cache invalidate at midnight UTC. Sorted tuples make key stable.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h_key = ",".join(sorted({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")}))
    w_key = ",".join(sorted({t.upper() for t in watchlist if t}))
    return f"{today}|{h_key}|{w_key}"


@router.post("/morning-brief")
async def morning_brief(req: MorningBriefRequest):
    """Personalized 'what matters for YOUR portfolio today' brief.

    Returns 3-5 categorized bullets, each with cited source + soft-stance language
    (tailwind/headwind/watch — never buy/sell, since unregistered RA).
    """
    # Resolve demo mode for cold-start users
    demo_mode = not req.positions and not req.watchlist_tickers
    if demo_mode:
        raw_positions = _DEMO_HOLDINGS
        watchlist = _DEMO_WATCHLIST
    else:
        raw_positions = [
            {"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in req.positions
        ]
        watchlist = list(req.watchlist_tickers)

    cache_key = _brief_cache_key(raw_positions, watchlist)
    if not req.force_refresh and cache_key in _morning_brief_cache:
        return _morning_brief_cache[cache_key]

    if not ai_client.is_available():
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI client not configured.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        context = await asyncio.to_thread(
            grounding.build_morning_brief_context, raw_positions, watchlist
        )
    except Exception as e:
        logger.exception("morning brief context build failed")
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": f"Could not build context: {e}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    task = (
        "You are an analyst writing a personalized morning brief for an Indian retail investor. "
        "Generate 3-5 bullets that explain what matters TODAY for the user's specific universe "
        "(CONTEXT.holdings + CONTEXT.watchlist). Each bullet must reference a specific source id "
        "from CONTEXT (e.g. global_news[2], INFY_news[0], or sectors[i].sector). "
        "\n\n"
        "STRICT RULES:\n"
        "1. NEVER recommend buy/sell/hold. Use soft stance language: 'tailwind', 'headwind', "
        "'watch', 'neutral'. You are educational, not advisory.\n"
        "2. Each bullet's affected_tickers MUST be tickers that appear in CONTEXT.holdings or "
        "CONTEXT.watchlist. Do NOT mention other tickers.\n"
        "3. Prefer themes that connect a global/macro event to the user's specific holdings via "
        "sector or business model (e.g. US 10Y up → IT services headwind because they earn USD).\n"
        "4. Prioritize: stock-specific news for held tickers > sector moves > India macro > global macro.\n"
        "5. Keep each bullet's body under 220 characters. Headline under 80 characters.\n"
        "6. If the user has zero holdings (CONTEXT.user_universe.holdings_count=0), still produce "
        "general market-flavored bullets covering the watchlist + indices."
    )
    schema = """{
  "items": [
    {
      "category": "macro" | "sector" | "stock_specific" | "global" | "earnings",
      "headline": str,
      "body": { "text": str, "source": str },
      "affected_tickers": [ str ],
      "stance": "tailwind" | "headwind" | "watch" | "neutral"
    }
  ],
  "market_summary": { "text": str, "source": str } | null,
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.generate_grounded_json, task, context, schema, 1024
            ),
            timeout=45,
        )
    except asyncio.TimeoutError:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "Generation timed out.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if not data:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI returned unparseable response.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Validate affected_tickers against the user's actual universe — defense against
    # hallucinated symbols. Drop any ticker not in CONTEXT.
    universe = {h["ticker"] for h in context.get("holdings", [])} | {
        w["ticker"] for w in context.get("watchlist", [])
    }
    items = data.get("items") or []
    cleaned_items: list[dict] = []
    for it in items[:5]:
        affected = [t for t in (it.get("affected_tickers") or []) if t in universe]
        cleaned_items.append({
            "category": it.get("category", "macro"),
            "headline": (it.get("headline") or "").strip()[:120],
            "body": it.get("body") or {"text": "", "source": ""},
            "affected_tickers": affected,
            "stance": it.get("stance", "neutral"),
        })

    payload = with_disclaimer({
        "demo_mode": demo_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": cleaned_items,
        "market_summary": data.get("market_summary"),
        "market_snapshot": {
            "indices": context.get("indices", {}),
            "sectors_top_3_movers": sorted(
                context.get("sectors", []),
                key=lambda s: abs(s.get("change_percent") or 0),
                reverse=True,
            )[:3],
        },
        "user_universe": context.get("user_universe", {}),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
    })

    _morning_brief_cache[cache_key] = payload
    return payload


# ---------------------------------------------------------------------------
# News-Impact Feed — the USP. Every news item annotated with portfolio impact.
#
# This is the killer feature: instead of one daily brief, we annotate each
# news headline with which of the user's tickers it touches, in which direction,
# at what impact level, and why. That's what nobody else in the Indian market
# does on the front page.
# ---------------------------------------------------------------------------
_news_feed_cache: TTLCache = TTLCache(maxsize=200, ttl=60 * 60)  # 1 hour


class NewsFeedRequest(BaseModel):
    positions: list[PositionIn] = []
    watchlist_tickers: list[str] = []
    force_refresh: bool = False


def _news_feed_cache_key(positions: list[dict], watchlist: list[str]) -> str:
    # 1-hour bucket keeps the feed feeling live but avoids regen for every page load.
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    h_key = ",".join(sorted({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")}))
    w_key = ",".join(sorted({t.upper() for t in watchlist if t}))
    return f"{bucket}|{h_key}|{w_key}"


# Thread pool for parallel quote fetching when building the per-user holdings
# snapshot. Sized small — each lookup is in market_data's 5-min cache so most
# requests resolve instantly anyway.
_holdings_pool = ThreadPoolExecutor(max_workers=12)


def _build_holdings_today(positions: list[dict]) -> dict:
    """Per-ticker live snapshot enriched with this user's specific economics:
        { ticker: {current_price, change_percent, quantity,
                   current_value_inr, day_pnl_inr, weight_pct} }

    Powers the "your stake" personalization strip on every news row + mover —
    so a "BANKBARODA surged 4.6%" headline shows the user "+₹570 today, 1.7%
    of your portfolio" instead of leaving them to do the math.

    Quotes are pulled via market_data.get_live_quote which has a 5-minute TTL,
    so this typically completes in <50ms even for 30+ tickers. Failed lookups
    are silently dropped — the consumer falls back to invested-only display.
    """
    if not positions:
        return {}

    def _fetch(ticker: str) -> tuple[str, dict | None]:
        try:
            return ticker, market_data.get_live_quote(ticker)
        except Exception:
            return ticker, None

    tickers = [(p.get("ticker") or "").upper() for p in positions if p.get("ticker")]
    if not tickers:
        return {}

    quotes: dict[str, dict] = {}
    for ticker, q in _holdings_pool.map(_fetch, tickers):
        if q and q.get("current_price"):
            quotes[ticker] = q

    enriched: dict[str, dict] = {}
    total_value = 0.0
    for p in positions:
        t = (p.get("ticker") or "").upper()
        if not t:
            continue
        q = quotes.get(t)
        if not q:
            continue
        qty = float(p.get("quantity") or 0)
        current_price = float(q["current_price"])
        change_pct = float(q.get("change_percent") or 0)
        current_value = qty * current_price
        # Reverse out the previous close from the % change to compute today's
        # absolute ₹ delta on this position. Guard against the degenerate
        # change_pct = -100% case (would divide by zero).
        if change_pct > -99.99:
            prev_close = current_price / (1 + change_pct / 100.0)
            day_pnl = qty * (current_price - prev_close)
        else:
            day_pnl = 0.0
        enriched[t] = {
            "current_price": round(current_price, 2),
            "change_percent": round(change_pct, 2),
            "quantity": qty,
            "current_value_inr": round(current_value, 2),
            "day_pnl_inr": round(day_pnl, 2),
        }
        total_value += current_value

    if total_value > 0:
        for t in enriched:
            enriched[t]["weight_pct"] = round(
                enriched[t]["current_value_inr"] / total_value * 100, 2
            )

    return enriched


def _flatten_news_for_ingest(context: dict) -> list[dict]:
    """Same as _collect_candidate_news but includes snippets — used for
    embedding into the vector store. Output schema matches what
    vector_store.ingest_news_items() expects.
    """
    out: list[dict] = []
    for h in context.get("holdings", []):
        for n in h.get("news", []):
            out.append({
                "headline": n.get("headline"),
                "snippet": n.get("snippet"),
                "source": n.get("source"),
                "scope": "stock_specific",
                "scope_ticker": h.get("ticker"),
            })
    for w in context.get("watchlist", []):
        for n in w.get("news", []):
            out.append({
                "headline": n.get("headline"),
                "snippet": n.get("snippet"),
                "source": n.get("source"),
                "scope": "stock_specific",
                "scope_ticker": w.get("ticker"),
            })
    for n in context.get("india_headlines", []):
        out.append({
            "headline": n.get("headline"),
            "snippet": n.get("snippet"),
            "source": n.get("source"),
            "scope": "macro",
        })
    for n in context.get("global_headlines", []):
        out.append({
            "headline": n.get("headline"),
            "snippet": n.get("snippet"),
            "source": n.get("source"),
            "scope": "global",
            "country": n.get("country"),
        })
    # Policy items (PIB/RBI). Embedded so semantic search surfaces "PLI scheme"
    # against TATA STEEL even when the keyword annotator misses the link.
    for n in context.get("policy_headlines", []):
        out.append({
            "headline": n.get("headline"),
            "snippet": n.get("snippet"),
            "source": n.get("source"),
            "scope": n.get("scope") or "policy",
        })
    return out


def _collect_candidate_news(context: dict) -> list[dict]:
    """Flatten all news available in the morning-brief context into a single list.

    Stock-specific news is guaranteed relevant (it's about a user's ticker) so
    we keep ALL of it. Macro/global are capped to keep token budget bounded.
    Final cap (90) is sized for ~50-stock universes on gpt-4o-mini's 128k context.
    """
    candidates: list[dict] = []

    # Per-holding ticker news — HIGHEST priority. Take all available.
    for h in context.get("holdings", []):
        for n in h.get("news", []):
            candidates.append({
                "id": n.get("id"),
                "headline": n.get("headline"),
                "source": n.get("source"),
                "scope": "stock_specific",
                "scope_ticker": h.get("ticker"),
            })

    # Per-watchlist ticker news — also guaranteed relevant.
    for w in context.get("watchlist", []):
        for n in w.get("news", []):
            candidates.append({
                "id": n.get("id"),
                "headline": n.get("headline"),
                "source": n.get("source"),
                "scope": "stock_specific",
                "scope_ticker": w.get("ticker"),
            })

    # India macro headlines — broader signal, smaller share.
    for n in context.get("india_headlines", [])[:8]:
        candidates.append({
            "id": n.get("id"),
            "headline": n.get("headline"),
            "source": n.get("source"),
            "scope": "macro",
            "scope_ticker": None,
        })

    # Global headlines (overnight) — most relevant for IT/Pharma/Auto exposure.
    for n in context.get("global_headlines", [])[:10]:
        candidates.append({
            "id": n.get("id"),
            "headline": n.get("headline"),
            "source": n.get("source"),
            "scope": "global",
            "scope_ticker": None,
            "country": n.get("country"),
        })

    # Policy / regulatory items — PIB government press releases + RBI. The
    # annotator maps these to user holdings via affected_sectors when no
    # specific ticker is named (e.g. "PLI expansion to specialty steel" hits
    # JSWSTEEL/TATASTEEL/JINDALSTEL). Cap at 12 — they're high-signal-density
    # so the LLM rarely needs more than the most-recent ones.
    for n in context.get("policy_headlines", [])[:12]:
        candidates.append({
            "id": n.get("id"),
            "headline": n.get("headline"),
            "source": n.get("source"),
            "scope": n.get("scope") or "policy",        # policy_pib | policy_rbi
            "scope_ticker": None,
            "affected_sectors": n.get("affected_sectors") or [],
        })

    return candidates[:100]  # bumped from 90 to absorb the policy stream


def _merge_semantic_into_candidates(
    base: list[dict],
    semantic_hits: list[dict],
) -> list[dict]:
    """Merge semantic-retrieval results into the base candidate list. Semantic
    hits surface news affecting a user's stock even when the headline doesn't
    name it (e.g. 'renewable subsidies' → TATAPOWER). We dedup by headline
    text so the same news doesn't appear twice when both pipelines catch it.

    Each semantic hit carries an `affected_ticker` (the user's stock that
    matched closest) — we pass that through to the LLM as a strong hint.
    """
    if not semantic_hits:
        return base

    seen_headlines = {(c.get("headline") or "").strip().lower() for c in base}
    extras: list[dict] = []
    for h in semantic_hits:
        headline = (h.get("headline") or "").strip()
        if not headline or headline.lower() in seen_headlines:
            continue
        seen_headlines.add(headline.lower())
        extras.append({
            "id": f"semantic[{h.get('id')}]",
            "headline": headline,
            "source": h.get("source"),
            "scope": h.get("scope") or "macro",
            "scope_ticker": h.get("affected_ticker"),
            "semantic_match_ticker": h.get("affected_ticker"),
            "semantic_similarity": round(float(h.get("similarity") or 0), 3),
        })
    return (base + extras)[:120]  # bump cap a bit since semantic adds value


@router.post("/news-feed")
async def news_feed(req: NewsFeedRequest, background: BackgroundTasks):
    """Annotated news stream — every relevant headline scored against the user's portfolio.

    Returns items with: impact_level, direction, affected_tickers (from user's universe),
    one-sentence reason, source citation. Items with no portfolio relevance are filtered out.

    Pipeline:
      1. Build RSS-based context (per-holding news + India + global headlines).
      2. Fire-and-forget background: embed fresh news into pgvector (idempotent).
      3. Query pgvector for SEMANTICALLY similar news on the user's universe —
         this surfaces hits the RSS keyword search misses (e.g. "renewable
         subsidies" mapping to TATAPOWER even when not named).
      4. Merge both candidate sets, dedup by headline.
      5. Send to LLM for annotation.
    """
    demo_mode = not req.positions and not req.watchlist_tickers
    if demo_mode:
        raw_positions = _DEMO_HOLDINGS
        watchlist = _DEMO_WATCHLIST
    else:
        raw_positions = [
            {"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in req.positions
        ]
        watchlist = list(req.watchlist_tickers)

    cache_key = _news_feed_cache_key(raw_positions, watchlist)
    if not req.force_refresh and cache_key in _news_feed_cache:
        return _news_feed_cache[cache_key]

    if not ai_client.is_available():
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI client not configured.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        context = await asyncio.to_thread(
            grounding.build_morning_brief_context, raw_positions, watchlist
        )
    except Exception as e:
        logger.exception("news feed context build failed")
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": f"Context build failed: {e}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # --- Fire-and-forget: feed today's news into the vector store ---
    # Caller doesn't wait. Idempotent via content_hash. Steady-state: only
    # genuinely new headlines pay the embedding cost.
    if vector_store.is_available():
        background.add_task(
            vector_store.ingest_news_items,
            _flatten_news_for_ingest(context),
        )

    candidates = _collect_candidate_news(context)

    # --- Semantic retrieval over pgvector ---
    # Returns news matching the SHAPE of user's stocks even when the headline
    # never names them. THIS is the wedge we built pgvector for.
    user_holdings = [h["ticker"] for h in context.get("holdings", [])]
    user_watchlist = [w["ticker"] for w in context.get("watchlist", [])]
    universe = user_holdings + user_watchlist
    semantic_hits = []
    if vector_store.is_available() and universe:
        try:
            semantic_hits = await asyncio.to_thread(
                vector_store.match_news_for_tickers,
                universe,
                40,    # match_count — fetch enough to enrich the LLM context
                48,    # recency_hours
                0.55,  # cosine similarity threshold (0.55 = "clearly related")
            )
        except Exception as e:
            logger.warning(f"semantic retrieval failed: {e}")

    candidates = _merge_semantic_into_candidates(candidates, semantic_hits)

    if not candidates:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_universe": context.get("user_universe", {}),
        })

    # Compute technical state for every ticker the user could be exposed to.
    # This lets the LLM write reasons like "rally on weak volume — move may fade"
    # instead of "positive movement enhances sentiment" (which says nothing).
    from app.services import technicals as _tech
    universe_set = list({*user_holdings, *user_watchlist})
    tech_by_ticker: dict[str, dict] = {}
    try:
        raw_tech = await asyncio.to_thread(_tech.compute_signals_batch, universe_set)
        for tk, sig in (raw_tech or {}).items():
            keep = ("rsi_zone", "vol_zone", "momentum_state", "sma_state", "pct_from_20d_high")
            tight = {k: sig.get(k) for k in keep if sig.get(k) is not None}
            if tight:
                tech_by_ticker[tk] = tight
    except Exception as e:
        logger.warning("technicals batch failed for news feed: %s", e)

    # holdings_by_sector — used by the LLM to map a policy item's
    # `affected_sectors` to the user's specific tickers in that sector.
    # Lets a "PLI expansion to specialty steel" PIB release flag JSWSTEEL,
    # TATASTEEL, JINDALSTEL even though the headline names none of them.
    holdings_by_sector: dict[str, list[str]] = {}
    for h in context.get("holdings", []):
        sec = (h.get("sector") or "Unknown")
        holdings_by_sector.setdefault(sec, []).append(h.get("ticker"))

    # Build a slim CONTEXT for batch annotation.
    annotation_ctx = {
        "user_holdings": user_holdings,
        "user_watchlist": user_watchlist,
        "user_holdings_by_sector": holdings_by_sector,
        "sectors_today": [
            {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
            for s in context.get("sectors", [])
        ],
        "user_universe_technicals": tech_by_ticker,
        "candidate_news": candidates,
    }

    task = (
        "For EACH item in CONTEXT.candidate_news, decide whether it materially affects "
        "the user's portfolio (CONTEXT.user_holdings + CONTEXT.user_watchlist). For items "
        "that DO affect the portfolio, output an annotation. SKIP items that don't.\n\n"
        "STRICT RULES:\n"
        "1. affected_tickers MUST be a subset of CONTEXT.user_holdings + CONTEXT.user_watchlist. "
        "Never invent tickers.\n"
        "2. impact_level: 'high' if it directly hits a held name or a sector with >20% portfolio "
        "weight, 'medium' if mild sector/macro effect, 'low' if tangential. Skip if no impact.\n"
        "3. direction: 'positive' (tailwind for affected tickers), 'negative' (headwind), 'mixed' "
        "(some up some down).\n"
        "4. reason: ONE concrete sentence (<200 chars). MUST cite both (a) the news mechanism AND "
        "(b) a relevant technical fact from CONTEXT.user_universe_technicals for at least one "
        "affected ticker. Example: 'PSB profits beat — HDFCBANK is below SMA50 with momentum "
        "extending_down, so this could trigger a sector-led mean-reversion bounce.' BANNED phrases: "
        "'may enhance sentiment', 'could affect', 'positive movement enhances'. Be specific.\n"
        "5. technical_context: short string (<120 chars) summarizing the technical state of the "
        "PRIMARY affected ticker (rsi_zone + vol_zone + momentum_state + sma_state). If no "
        "technicals available for that ticker, set to null. Example: 'RSI overbought; vol 1.8x avg; "
        "extending_up; above SMA50.'\n"
        "6. category: 'stock_specific' (single ticker news), 'sector' (sector-wide), 'macro' "
        "(India macro), 'global' (overseas event with India impact).\n"
        "7. Order output by impact_level (high → medium → low). Cap at 20 items — "
        "the top 20 most relevant beat a long tail every time.\n"
        "8. For users with 20+ holdings, lean toward keeping items even at 'low' impact — "
        "the user wants breadth of coverage across their portfolio, not just headline events.\n"
        "9. Some candidates carry `semantic_match_ticker` + `semantic_similarity` (0-1). "
        "These are surfaced by vector search — they're news that doesn't NAME the ticker but "
        "is semantically close to its business. Treat these as valid signal: include the named "
        "ticker in affected_tickers if the transmission mechanism is real. Higher similarity "
        "(>0.7) = stronger signal.\n"
        "9b. POLICY ITEMS — if a candidate has scope='policy_pib' or 'policy_rbi' it carries "
        "`affected_sectors`. These items are government press releases / RBI notifications and "
        "rarely name specific companies. Map them to the user's holdings by intersecting the "
        "item's affected_sectors with CONTEXT.user_holdings_by_sector — every matched ticker "
        "goes into affected_tickers. Set category='macro'. Example: a PIB release with "
        "affected_sectors=['Banking & Finance'] should set affected_tickers to ALL user "
        "holdings under Banking. If no sector overlap with the user's portfolio, SKIP the item.\n"
        "10. DIRECTION DISCIPLINE — DEFAULT TO 'mixed' when in doubt. Only emit 'positive' or "
        "'negative' when (a) the news is unambiguously directional AND (b) the affected ticker's "
        "technical state in CONTEXT.user_universe_technicals is consistent with the direction "
        "(e.g. positive news + momentum extending_up + above SMA50). If technicals contradict the "
        "news, call it 'mixed'. The system will then drop low-conviction calls — better to under-"
        "promise than to issue a confident wrong direction. BANNED words: 'will', 'should', 'expected to'."
    )
    schema = """{
  "items": [
    {
      "news_id": str,
      "headline": str,
      "source": str,
      "category": "stock_specific" | "sector" | "macro" | "global",
      "impact_level": "high" | "medium" | "low",
      "direction": "positive" | "negative" | "mixed",
      "affected_tickers": [ str ],
      "reason": str,
      "technical_context": str | null
    }
  ],
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(
                # 2400 tokens: 20 items × ~120 tokens each. Reduced from 3500
                # after capping items at 20 → faster LLM completion.
                ai_client.generate_grounded_json, task, annotation_ctx, schema, 2400
            ),
            # 110s on Render's free tier — OpenAI from Render is 2-3× slower
            # than from a laptop and the request retry loop after a premature
            # timeout costs the user more than just waiting once.
            timeout=110,
        )
    except asyncio.TimeoutError:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "Generation timed out.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if not data:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI returned unparseable response.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Index the original candidates by id so we can re-attach similarity scores
    # and URLs that the LLM strips out of its output.
    candidate_by_id = {c.get("id"): c for c in candidates if c.get("id")}

    universe = set(user_holdings) | set(user_watchlist)
    cleaned: list[dict] = []
    for it in (data.get("items") or [])[:20]:
        affected = [t for t in (it.get("affected_tickers") or []) if t in universe]
        if not affected:
            continue  # if no real impact on user, drop it
        tc = it.get("technical_context")
        nid = it.get("news_id")
        orig = candidate_by_id.get(nid) or {}
        # Forward `scope` + `affected_sectors` from the original candidate so
        # the frontend can render a distinct POLICY badge + sector chips for
        # PIB/RBI items. Plain news items have scope='stock_specific'/'macro'/
        # 'global' and no affected_sectors — those fields just stay null.
        cleaned.append({
            "news_id": nid,
            "headline": (it.get("headline") or "").strip()[:200],
            "source": it.get("source") or orig.get("source"),
            "url": orig.get("url"),
            "category": it.get("category", "macro"),
            "impact_level": it.get("impact_level", "low"),
            "direction": it.get("direction", "mixed"),
            "affected_tickers": affected,
            "reason": (it.get("reason") or "").strip()[:240],
            "technical_context": (tc or None) and tc.strip()[:140],
            "semantic_match_ticker": orig.get("semantic_match_ticker"),
            "semantic_similarity": orig.get("semantic_similarity"),
            "snippet": (orig.get("snippet") or "")[:280] or None,
            "scope": orig.get("scope"),
            "affected_sectors": orig.get("affected_sectors") or [],
        })

    # Sort: high → medium → low (already requested in prompt but enforce server-side).
    impact_order = {"high": 0, "medium": 1, "low": 2}
    cleaned.sort(key=lambda x: impact_order.get(x["impact_level"], 3))

    # Multi-signal ensemble — same selectivity rule as Tomorrow. Override each
    # item's direction with consensus of news + technicals + flow, attach a
    # conviction score. We keep low-conviction items in the ledger (for
    # backtesting) but drop them from the user-facing payload.
    flows_for_news = ((context.get("market") or {}).get("flows")
                       if isinstance(context.get("market"), dict) else None)
    hidden_news_count = _apply_ensemble_to_news_items(
        cleaned, tech_by_ticker, context.get("sectors"), flows_for_news,
    )

    # Outcome ledger — fire-and-forget log of every scoreable news item as a
    # forward-looking prediction (one row per item × affected ticker). Mixed
    # direction items are skipped inside the helper. UPSERT keyed by
    # news_feed:{ticker}:{news_id}:{date} so concurrent users don't duplicate.
    if outcome_ledger.is_available():
        background.add_task(_log_news_feed_predictions, cleaned, tech_by_ticker)

    # Filter for the user-facing list AFTER logging (so the ledger sees everything).
    user_items = [it for it in cleaned if not it.get("hidden_low_conviction")]

    # Per-user live snapshot. Cheap because market_data.get_live_quote is cached.
    # In demo_mode `raw_positions` is _DEMO_HOLDINGS so the demo viewer also
    # gets meaningful "your stake" numbers — no special-casing needed.
    holdings_today = _build_holdings_today(raw_positions)

    payload = with_disclaimer({
        "demo_mode": demo_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": user_items,
        "hidden_low_conviction_count": hidden_news_count,
        "min_conviction": signal_ensemble.MIN_CONVICTION_FOR_USER,
        "user_universe": context.get("user_universe", {}),
        # Forward per-ticker technical state so the click-through detail modal
        # can render each affected holding's current chart situation.
        "universe_technicals": tech_by_ticker,
        # Per-holding live values — frontend renders the "your stake" strip
        # on each news row from this map.
        "holdings_today": holdings_today,
        "data_gaps": data.get("data_gaps", []),
    })
    _news_feed_cache[cache_key] = payload
    return payload


# ---------------------------------------------------------------------------
# Market Summary — 60+ line narrative giving the user the day's full story
# in plain English. Sits to the LEFT of the news feed in the dashboard.
# ---------------------------------------------------------------------------
_market_summary_cache: TTLCache = TTLCache(maxsize=200, ttl=4 * 60 * 60)  # 4 hours


def _slim_summary_context(ctx: dict) -> dict:
    """Compact view of build_morning_brief_context for the market_summary LLM.
    Cuts input from ~12K tokens to ~4K — under Groq's 12K TPM cap and ~3× faster
    for OpenAI too. We drop snippets, cap headlines, and trim per-holding news
    to one item; the narrative call doesn't need the full firehose.
    """
    def _slim_news(items, limit, keep_snippet=False):
        out = []
        for n in (items or [])[:limit]:
            entry = {"id": n.get("id"), "source": n.get("source"), "headline": n.get("headline")}
            if keep_snippet and n.get("snippet"):
                entry["snippet"] = (n["snippet"] or "")[:160]
            out.append(entry)
        return out

    slim = {
        "user_universe": ctx.get("user_universe", {}),
        "indices": ctx.get("indices", {}),
        # Keep sector returns — they're small (≤17 entries × 3 fields).
        "sectors": [
            {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
            for s in (ctx.get("sectors") or [])
        ],
        # Cap headlines. ID prefix is preserved so source-citation rules still
        # work (the prompt expects `global_news[i]`/`india_news[i]`).
        "india_headlines": _slim_news(ctx.get("india_headlines"), limit=5),
        "global_headlines": _slim_news(ctx.get("global_headlines"), limit=8),
        # Policy headlines — PIB / RBI. Carry their own scope tag the LLM can
        # cite for `watch_today` ("RBI MPC tomorrow per policy_news[2]") instead
        # of saying "investors should watch for RBI announcements."
        "policy_headlines": _slim_news(ctx.get("policy_headlines"), limit=6),
    }
    # Holdings: ticker, name, sector, 1 news item, + upcoming_earnings (the
    # concrete date the LLM cites in watch_today/tomorrow_setup instead of
    # falling back on "earnings reports may provide insights").
    holdings = []
    for h in (ctx.get("holdings") or [])[:15]:
        slot = {
            "ticker": h.get("ticker"),
            "name": h.get("name"),
            "sector": h.get("sector"),
            "news": _slim_news(h.get("news"), limit=1),
        }
        ue = h.get("upcoming_earnings")
        if ue:
            slot["upcoming_earnings"] = ue
        holdings.append(slot)
    slim["holdings"] = holdings
    # Watchlist: ticker + sector + upcoming earnings (no news to keep payload small).
    watchlist = []
    for w in (ctx.get("watchlist") or [])[:10]:
        slot = {"ticker": w.get("ticker"), "sector": w.get("sector")}
        ue = w.get("upcoming_earnings")
        if ue:
            slot["upcoming_earnings"] = ue
        watchlist.append(slot)
    slim["watchlist"] = watchlist

    # Roll up all upcoming earnings across holdings + watchlist into one
    # `upcoming_events` list the LLM can scan at a glance. Sorted by days_ahead.
    # This is the single biggest fix for filler text in watch_today /
    # tomorrow_setup — the model now has a concrete calendar to cite from.
    rolled: list[dict] = []
    for w in (holdings + watchlist):
        ue = w.get("upcoming_earnings")
        if ue and isinstance(ue, dict) and ue.get("date"):
            rolled.append({
                "ticker": w.get("ticker"),
                "name": w.get("name") or w.get("ticker"),
                "event": "earnings",
                "date": ue.get("date"),
                "days_ahead": ue.get("days_ahead"),
            })
    rolled.sort(key=lambda x: x.get("days_ahead") or 999)
    slim["upcoming_events"] = rolled[:12]
    return slim


class MarketSummaryRequest(BaseModel):
    positions: list[PositionIn] = []
    watchlist_tickers: list[str] = []
    force_refresh: bool = False


def _summary_cache_key(positions: list[dict], watchlist: list[str]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h_key = ",".join(sorted({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")}))
    w_key = ",".join(sorted({t.upper() for t in watchlist if t}))
    # `v2` — bumped after the prompt rewrite that bans filler phrases and
    # requires concrete dated events in watch_today/tomorrow_setup. Stale
    # cached payloads written under the old prompt would still serve filler;
    # the bump invalidates them in one line.
    return f"summary|v2|{today}|{h_key}|{w_key}"


@router.post("/market-summary")
async def market_summary(req: MarketSummaryRequest):
    """Long-form daily market narrative — 5-7 sections, ~60+ lines total.

    Newspaper-style explainer the user reads in 2 minutes to understand:
      - Overnight global moves and what they signal
      - Indian market open + sector breadth
      - Specific catalysts hitting the user's holdings
      - Sector-wide pressures or tailwinds
      - What to watch for the rest of the session and tomorrow
    """
    demo_mode = not req.positions and not req.watchlist_tickers
    if demo_mode:
        raw_positions = _DEMO_HOLDINGS
        watchlist = _DEMO_WATCHLIST
    else:
        raw_positions = [
            {"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in req.positions
        ]
        watchlist = list(req.watchlist_tickers)

    cache_key = _summary_cache_key(raw_positions, watchlist)
    if not req.force_refresh and cache_key in _market_summary_cache:
        return _market_summary_cache[cache_key]

    if not ai_client.is_available():
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": "AI client not configured.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        context = await asyncio.to_thread(
            grounding.build_morning_brief_context, raw_positions, watchlist
        )
    except Exception as e:
        logger.exception("market summary context build failed")
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": f"Context build failed: {e}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    user_holdings = [h["ticker"] for h in context.get("holdings", [])]
    user_watchlist = [w["ticker"] for w in context.get("watchlist", [])]

    task = (
        "Write a comprehensive daily market summary for an Indian retail investor with "
        "the universe shown in CONTEXT. The output must read like a senior analyst's "
        "morning note — plain English, complete sentences, narrative flow.\n\n"
        "STRUCTURE — emit EXACTLY these 6 sections in this order. Each section has a\n"
        "STRICTLY ENFORCED scope (what it covers) and exclusion (what belongs elsewhere).\n"
        "Sections must NOT cover the same evidence — if a fact appears in one section,\n"
        "it cannot reappear in another. Use the SAME headline / news id at most ONCE\n"
        "across the entire brief.\n\n"
        "  1. 'overnight'         — what happened in US/EU/Asia LAST NIGHT (Wall Street\n"
        "                           close, Asia-Pacific overnight, Europe close).\n"
        "                           ALLOWED: global_news[*], indices (US/EU/Asia).\n"
        "                           DO NOT include: India market open, Indian holdings,\n"
        "                           or 'what to watch tonight' (that's tomorrow_setup).\n"
        "                           ~3-4 sentences.\n"
        "  2. 'india_open'        — Nifty/Sensex levels and DOMESTIC breadth this morning.\n"
        "                           ALLOWED: indices.nifty_50/sensex/midcap, sectors[*]\n"
        "                           returns, india_news[*] about the broad market.\n"
        "                           DO NOT include: global overnight (overnight), any\n"
        "                           single holding by name (your_portfolio).\n"
        "                           ~3-4 sentences.\n"
        "  3. 'your_portfolio'    — direct catalysts hitting CONTEXT.holdings; name\n"
        "                           specific tickers and which {TICKER}_news[*] item or\n"
        "                           sector move drove them. THIS IS THE LONGEST SECTION.\n"
        "                           ALLOWED: per-ticker news ids, holdings.\n"
        "                           DO NOT include: generic sector commentary (that's\n"
        "                           sector_pulse), upcoming-event teasers (watch_today).\n"
        "                           ~5-7 sentences.\n"
        "  4. 'sector_pulse'      — sector-wide forces relevant to the user's exposure.\n"
        "                           Reference user_universe.sector_exposure_pct + the\n"
        "                           sectors[*] return data. Talk about the SECTOR as a\n"
        "                           whole, not individual tickers.\n"
        "                           DO NOT include: per-ticker stories (your_portfolio),\n"
        "                           any global news (overnight).\n"
        "                           ~3-5 sentences.\n"
        "  5. 'watch_today'       — events scheduled IN INDIA in the next 0-2 days.\n"
        "                           SOURCES (one of these MUST be cited or this section\n"
        "                           is just 1 short honest sentence):\n"
        "                             • upcoming_events[*] with days_ahead ≤ 2 → name\n"
        "                               the TICKER + EXACT DATE ('TCS earnings 22 May\n"
        "                               per upcoming_events[1]').\n"
        "                             • policy_news[*] dated today/tomorrow → cite by id.\n"
        "                           If neither has any item: write ONE sentence — 'No\n"
        "                           portfolio earnings or scheduled policy events in the\n"
        "                           next 48 hours' — and STOP. Do not pad.\n"
        "  6. 'tomorrow_setup'    — what to watch TONIGHT (US session, Fed/Powell, US\n"
        "                           data, US earnings) AND upcoming_events[*] with\n"
        "                           days_ahead between 1 and 5. Name specific holdings\n"
        "                           and their dates.\n"
        "                           DO NOT include: anything that already happened\n"
        "                           overnight (that's section 1), any India-today events\n"
        "                           (that's watch_today).\n"
        "                           If thin: ONE honest sentence. No filler.\n\n"
        "STRICT RULES:\n"
        "1. NEVER recommend buy/sell/hold. Use stance language only ('tailwind',\n"
        "   'headwind', 'watch', 'caution'). Educational, not advisory.\n"
        "2. Every analytical claim must reference a specific id from CONTEXT (e.g.\n"
        "   global_news[2], INFY_news[0], sectors[i]). Cite inline as '(per global_news[2])'.\n"
        "3. Mention the user's specific tickers by name where relevant — this is\n"
        "   personalized, not generic.\n"
        "4. **NO CROSS-SECTION REPETITION.** Each evidence id (a news[i] or sectors[i])\n"
        "   may be cited in AT MOST ONE section. If you find yourself wanting to reuse\n"
        "   the same point in a second section, that's a signal the second section\n"
        "   has nothing to add and should be SHORTER, not a paraphrase of the first.\n"
        "5. **NO REPHRASED PARAPHRASES.** Two sections must not say the same thing in\n"
        "   different words. The reader will notice and the brief becomes worthless.\n"
        "6. Total output across all sections should be ~60 lines / ~500-700 words.\n"
        "   Concise, readable, no fluff.\n"
        "7. If CONTEXT has thin data for a section, write a SHORTER section (1-2\n"
        "   sentences) explicitly saying the calendar is light. NEVER pad with content\n"
        "   already covered elsewhere.\n"
        "8. **BANNED FILLER PHRASES** — these are zero-information templates and will\n"
        "   make the brief look generated. Never use:\n"
        "     • 'investors should keep an eye on...' / '...should monitor...'\n"
        "     • '...may provide further insights...' / '...could provide direction...'\n"
        "     • 'market participants remain vigilant' / '...remain cautious'\n"
        "     • 'looking ahead...' / 'going forward...'\n"
        "     • 'potential policy announcements' (cite a SPECIFIC policy_news[i] or omit)\n"
        "     • 'earnings reports from various companies' (NAME the tickers + dates)\n"
        "     • 'sectors exposed to international trends' (NAME the sector)\n"
        "   Every sentence must carry SPECIFIC data — a ticker, a date, a percentage,\n"
        "   a named policy, or a news id. Otherwise delete the sentence."
    )
    schema = """{
  "sections": [
    {
      "id": "overnight" | "india_open" | "your_portfolio" | "sector_pulse" | "watch_today" | "tomorrow_setup",
      "title": str,                                  // human-friendly, e.g. "Overnight"
      "body": str,                                   // multi-sentence paragraph(s), inline source citations
      "stance": "tailwind" | "headwind" | "mixed" | "neutral",
      "key_tickers": [ str ]                         // tickers from CONTEXT mentioned in body
    }
  ],
  "headline": str,                                   // one-line takeaway for the whole day, <100 chars
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    # Trim the context fed to the LLM so the prompt stays small. The morning-
    # brief builder packs ~12K tokens of news + per-holding context which
    # blows past Groq's free-tier 12K TPM and slows OpenAI too. We don't need
    # all of it for a narrative — cap headlines + drop snippets for speed.
    slim_context = _slim_summary_context(context)

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.generate_grounded_json, task, slim_context, schema, 2200
            ),
            # 90s — narrative output is faster than news annotation but Render
            # IO + OpenAI latency still costs vs local. Better to wait than
            # serve an error and force the user to retry.
            timeout=90,
        )
    except asyncio.TimeoutError:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": "Generation timed out.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if not data:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": "AI returned unparseable response.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    universe = set(user_holdings) | set(user_watchlist)
    sections = []
    for s in (data.get("sections") or [])[:6]:
        key_tickers = [t for t in (s.get("key_tickers") or []) if t in universe]
        sections.append({
            "id": s.get("id", "overnight"),
            "title": (s.get("title") or s.get("id") or "Section").strip()[:80],
            "body": (s.get("body") or "").strip(),
            "stance": s.get("stance", "neutral"),
            "key_tickers": key_tickers,
        })

    payload = with_disclaimer({
        "demo_mode": demo_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": (data.get("headline") or "").strip()[:200],
        "sections": sections,
        "user_universe": context.get("user_universe", {}),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
    })
    _market_summary_cache[cache_key] = payload
    return payload


# ---------------------------------------------------------------------------
# Demo prewarm — keeps the cold-start caches hot so a brand-new visitor (or
# logged-in user with empty portfolio) sees a populated dashboard instantly.
#
# Hit this from cron-job.org every 30 min:
#   POST https://fincontext.onrender.com/api/intelligence/prewarm-demo
#   Header: X-Admin-Token: <ADMIN_TOKEN from env>
# ---------------------------------------------------------------------------
_ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")


def _check_admin(token: str | None) -> None:
    if not _ADMIN_TOKEN:
        raise HTTPException(503, "ADMIN_TOKEN not configured.")
    if token != _ADMIN_TOKEN:
        raise HTTPException(401, "Invalid admin token.")


@router.post("/prewarm-demo")
async def prewarm_demo(x_admin_token: str | None = Header(default=None)):
    """Pre-compute the demo-mode caches (empty positions + empty watchlist) so
    first-time visitors / cold-start dashboards render instantly. Intended to
    be hit by an external cron every 30 min — frequent enough to keep the cache
    warm, infrequent enough to not pay LLM cost on every minute.

    Returns a per-endpoint status map so the cron's health check can flag
    silent failures.
    """
    _check_admin(x_admin_token)

    results: dict[str, str] = {}
    bg = BackgroundTasks()

    # 1. News Feed (demo mode — empty positions trigger _DEMO_HOLDINGS path).
    try:
        await news_feed(
            NewsFeedRequest(positions=[], watchlist_tickers=[], force_refresh=True),
            bg,
        )
        results["news_feed"] = "warmed"
    except Exception as e:
        logger.warning("prewarm news_feed failed: %s", e)
        results["news_feed"] = f"failed: {type(e).__name__}"

    # 2. Market Summary (also has demo path).
    try:
        await market_summary(
            MarketSummaryRequest(positions=[], watchlist_tickers=[], force_refresh=True),
        )
        results["market_summary"] = "warmed"
    except Exception as e:
        logger.warning("prewarm market_summary failed: %s", e)
        results["market_summary"] = f"failed: {type(e).__name__}"

    # 3. Movers + Portfolio Intelligence — these reject empty positions, so
    # we warm them with the demo holdings explicitly. Cache key matches what
    # `_movers_generator` would produce for a real user with the same
    # portfolio, but this is purely a warm-the-pump exercise: real users
    # with their own portfolios still get their own cached entries.
    demo_positions = [
        PositionIn(ticker=h["ticker"], quantity=h["quantity"], buy_price=h["buy_price"])
        for h in _DEMO_HOLDINGS
    ]
    for label, fn, req_cls in (
        ("movers", portfolio_movers, MoversRequest),
        ("portfolio_intelligence", portfolio_intelligence, IntelRequest),
    ):
        try:
            resp = await fn(req_cls(positions=demo_positions, force_refresh=True))
            # SSE response — drain the stream so the generator runs to completion
            # and writes its result into response_cache.
            if isinstance(resp, StreamingResponse):
                async for _chunk in resp.body_iterator:
                    pass
            results[label] = "warmed"
        except Exception as e:
            logger.warning("prewarm %s failed: %s", label, e)
            results[label] = f"failed: {type(e).__name__}"

    return {
        "results": results,
        "cache_stats": response_cache.stats(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/cache-stats")
async def cache_stats(x_admin_token: str | None = Header(default=None)):
    """Diagnostic — peek at the response cache to verify SWR is doing its job.
    Useful right after deploy to confirm cold-start, then again 5 min later to
    see hits accumulating."""
    _check_admin(x_admin_token)
    return response_cache.stats()
