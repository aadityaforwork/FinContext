"use client";

/**
 * ContextLayer — S2 hanging section head. The "what we actually built"
 * section, and the hand-off into MCPSection below it.
 *
 * Deliberately does NOT restate HowItWorks' four stages — that section
 * already covers the pipeline (compute → ground → verify → grade). This one
 * covers the *idea*: the grounded context block is a single artefact that
 * gets computed once and then served to two different consumers. That's the
 * thing worth marketing, and it's what makes the MCP server a natural
 * extension rather than a bolt-on.
 *
 * HONEST COPY: every field in FIELDS is a real key on the payload returned
 * by POST /api/analysis/context (see backend/app/routers/analysis.py's
 * stock_context handler and services/grounding.build_stock_context). The
 * descriptions paraphrase what each key actually holds — no invented
 * capabilities, no metrics.
 */

const FIELDS = [
  {
    key: "snapshot",
    body: "Live price and the fundamentals block — P/E, P/B, ROE, margin, debt/equity, revenue growth.",
  },
  {
    key: "peer_benchmark",
    body: "Sector-peer medians for each of those, plus where this stock ranks against them by percentile.",
  },
  {
    key: "scores",
    body: "Financial scores derived from the peer percentiles — computed in code, not estimated by a model.",
  },
  {
    key: "signals",
    body: "Rule-based strengths and concerns. Each one names the exact field it was drawn from.",
  },
  {
    key: "sector_alternatives",
    body: "Same-sector peers that score higher on ROE, so the comparison isn’t left implicit.",
  },
  {
    key: "news",
    body: "Recent headlines for the ticker, carried alongside the numbers rather than blended into them.",
  },
];

export default function ContextLayer() {
  return (
    <section id="context-layer" className="landing-section">
      <div className="context-layer__head">
        <h2 className="landing-h2">One context block, computed once</h2>
        <p className="landing-lede">
          Everything FinContext says about a stock is assembled first as a
          single structured object — deterministic numbers, peer comparisons,
          and rule-derived signals that each cite the field behind them. Only
          then does a model get involved, and only to narrate what&rsquo;s
          already there.
        </p>
      </div>

      <dl className="context-layer__list">
        {FIELDS.map((f, i) => (
          <div key={f.key} className="context-layer__row landing-reveal" style={{ "--i": i }}>
            <dt className="context-layer__key">{f.key}</dt>
            <dd className="context-layer__body">{f.body}</dd>
          </div>
        ))}
      </dl>

      <p className="context-layer__note">
        This is the same block our own Deep Dive is built from. Nothing is
        summarised or re-scored on the way out — which is exactly why it can be
        handed to something other than our own interface.
      </p>
    </section>
  );
}
