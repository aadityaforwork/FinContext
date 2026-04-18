"""
LLM Engine Service
===================
This module handles the language model generation pipeline.
It is STRICTLY DECOUPLED from the data ingestion layer (data_ingestion.py).

Architecture:
    data_ingestion.py → context docs → llm_engine.py → synthesized analysis
"""

import logging

from app.seed_data import STOCKS
from app.services import ai_client

logger = logging.getLogger(__name__)


def generate_analysis(ticker: str, context_docs: list[dict]) -> str:
    """
    Generate a synthesized analysis paragraph from retrieved context using Gemini.
    """
    stock = STOCKS.get(ticker)
    if not stock or not context_docs:
        return f"Insufficient data available for {ticker} analysis at this time."

    name = stock["name"]
    sector = stock["sector"]
    change = stock["change_percent"]
    direction = "gaining" if change > 0 else "declining" if change < 0 else "flat"

    if ai_client.is_available():
        context_text = "\n\n".join([
            f"[{d['source']}] {d['headline']}: {d['snippet']}"
            for d in context_docs
        ])

        prompt = f"""
You are a senior equity research analyst.
Analyze the following Indian stock based strictly on the provided recent news context, without hallucinating.

Stock: {name} ({ticker})
Sector: {sector}
Current momentum: {direction} ({abs(change):.1f}%)

Context Documents:
{context_text}

Instructions:
1. Synthesize the core catalyst driving recent movement based ONLY on the context.
2. Provide a cohesive narrative around sector headwinds or tailwinds.
3. Keep it professional, objective, and around 100-150 words. Format with markdown (bolding key entities). Do not add a title.
"""
        try:
            text = ai_client.generate_text(prompt, max_tokens=600)
            if text:
                return text
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")

    # Fallback to template if model fails or key is missing
    top_news = context_docs[0]
    supporting = context_docs[1] if len(context_docs) > 1 else None
    macro = context_docs[2] if len(context_docs) > 2 else None

    analysis_parts = [
        f"**{name} ({ticker})** is currently {direction} {abs(change):.1f}% "
        f"in the {sector} space. "
    ]

    analysis_parts.append(
        f"The primary catalyst appears to be: *\"{top_news['headline']}\"* "
        f"({top_news['source']}, {top_news['published_date']}). "
        f"{top_news['snippet'][:200]} "
    )

    if supporting:
        analysis_parts.append(
            f"Additionally, {supporting['source']} reports that "
            f"\"{supporting['headline'].lower()}\", which provides further "
            f"tailwinds for the stock. "
        )

    if macro:
        analysis_parts.append(
            f"From a macro perspective, {macro['snippet'][:150]}. "
        )

    analysis_parts.append(
        f"Given the current momentum and sector-level developments, "
        f"the near-term outlook for {name} remains "
        f"{'constructive' if change > 0 else 'cautious' if change < 0 else 'neutral'}. "
        f"Investors should monitor upcoming quarterly results and "
        f"policy developments for confirmation of these trends."
    )

    return "".join(analysis_parts)
