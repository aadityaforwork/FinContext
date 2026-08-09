"use client";

/**
 * MarketsTicker — studied DNA from a reference travel-booking page (a
 * live "departures board" strip: city codes + times + a pulsing live
 * dot, sitting above the main nav). Adapted honestly, not copied: real
 * exchange names the product's grounding pipeline actually watches for
 * overnight/global catalysts (see grounding.py's macro/global-spillover
 * sourcing), no fabricated live prices or index levels — the pulse marks
 * "this is what we track," not "here is a live feed."
 */
const MARKETS = ["NSE Mumbai", "Nasdaq New York", "Nikkei Tokyo", "Hang Seng Hong Kong", "FTSE London", "DAX Frankfurt"];

export default function MarketsTicker() {
  return (
    <div className="markets-ticker">
      <div className="markets-ticker__track">
        <span className="markets-ticker__label">
          <span className="pulse-dot markets-ticker__dot" aria-hidden="true" />
          Context Engine tracks
        </span>
        {MARKETS.map((m) => (
          <span key={m} className="markets-ticker__item">{m}</span>
        ))}
      </div>
    </div>
  );
}
