"use client";

/**
 * YourStake — the per-row personalization strip.
 * ----------------------------------------------
 * Drops onto any signal row (news item, mover, watch item, theme) and answers
 * the user's only real question: "what does this mean for ME?".
 *
 * Given a list of affected tickers + the backend's `holdings_today` map (live
 * prices × user qty), it computes the intersection with the user's portfolio
 * and renders one compact line:
 *
 *   "Your INFY: 14 sh · ₹21,400 · today +₹540 · 8.4% of portfolio"
 *   "Your 3 positions hit: ₹62,300 · today −₹820 · 22.1% of portfolio"
 *   "Not in your portfolio"  (when no overlap)
 *
 * Pure presentation — no fetching, no state. Pass `holdingsToday` from the
 * parent that already has it (NewsImpactFeed, PortfolioContextCard).
 */

function fmtINR(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "−" : "";
  return `${sign}₹${Math.abs(Math.round(n)).toLocaleString("en-IN")}`;
}

function fmtSignedINR(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "−";
  return `${sign}₹${Math.abs(Math.round(n)).toLocaleString("en-IN")}`;
}

/**
 * Given the affected tickers from a signal + the user's live holdings map,
 * return an aggregate breakdown the row can render.
 */
export function computeStake(tickers, holdingsToday) {
  if (!holdingsToday || !tickers?.length) {
    return { held: [], totalValue: 0, totalDayPnl: 0, totalWeight: 0 };
  }
  const held = [];
  let totalValue = 0;
  let totalDayPnl = 0;
  let totalWeight = 0;
  for (const t of tickers) {
    const key = (t || "").toUpperCase();
    const h = holdingsToday[key];
    if (!h) continue;
    held.push({ ticker: key, ...h });
    totalValue += h.current_value_inr || 0;
    totalDayPnl += h.day_pnl_inr || 0;
    totalWeight += h.weight_pct || 0;
  }
  return { held, totalValue, totalDayPnl, totalWeight: Math.round(totalWeight * 10) / 10 };
}

/**
 * <YourStake tickers={[...]} holdingsToday={...} variant="news" | "mover" />
 *
 * Variants only differ in the lead label ("Your stake" / "Contributed today").
 */
export default function YourStake({
  tickers,
  holdingsToday,
  variant = "news",
  showNotInPortfolio = false,
}) {
  const { held, totalValue, totalDayPnl, totalWeight } = computeStake(tickers, holdingsToday);

  if (held.length === 0) {
    if (!showNotInPortfolio) return null;
    return (
      <div style={baseRowStyle}>
        <span style={labelStyle}>Not in your portfolio</span>
      </div>
    );
  }

  const dayColor =
    totalDayPnl > 0 ? "var(--color-accent-green)"
    : totalDayPnl < 0 ? "var(--color-accent-red)"
    : "var(--color-text-muted)";

  // Single holding — show ticker + share count up front.
  if (held.length === 1) {
    const h = held[0];
    return (
      <div style={baseRowStyle}>
        <span style={labelStyle}>
          {variant === "mover" ? "Contributed today" : "Your stake"}
        </span>
        <span style={tickerStyle}>{h.ticker}</span>
        <span style={mutedStyle}>· {h.quantity} sh · {fmtINR(h.current_value_inr)}</span>
        <span style={{ ...numStyle, color: dayColor }}>
          · today {fmtSignedINR(totalDayPnl)}
        </span>
        {h.weight_pct != null && (
          <span style={mutedStyle}>· {h.weight_pct}% of portfolio</span>
        )}
      </div>
    );
  }

  // Multi-holding — collapse into an aggregate plus the list.
  const tickersStr = held.map((h) => h.ticker).join(", ");
  return (
    <div style={baseRowStyle}>
      <span style={labelStyle}>
        {variant === "mover" ? "Contributed today" : "Your stake"}
      </span>
      <span style={tickerStyle}>{held.length} positions</span>
      <span style={mutedStyle}>· {fmtINR(totalValue)}</span>
      <span style={{ ...numStyle, color: dayColor }}>
        · today {fmtSignedINR(totalDayPnl)}
      </span>
      <span style={mutedStyle}>· {totalWeight}% of portfolio</span>
      <span style={{ ...mutedStyle, fontStyle: "italic" }}>· {tickersStr}</span>
    </div>
  );
}

const baseRowStyle = {
  marginTop: "8px",
  display: "flex",
  flexWrap: "wrap",
  alignItems: "baseline",
  columnGap: "6px",
  rowGap: "2px",
  padding: "6px 10px",
  borderRadius: "6px",
  background: "rgba(99,102,241,0.05)",
  border: "1px solid rgba(99,102,241,0.18)",
  fontSize: "11.5px",
  lineHeight: 1.5,
};

const labelStyle = {
  fontSize: "9px",
  fontWeight: 700,
  color: "var(--color-accent-secondary)",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  marginRight: "2px",
};

const tickerStyle = {
  fontFamily: "var(--font-mono)",
  fontWeight: 700,
  color: "var(--color-text-primary)",
  fontSize: "11.5px",
};

const mutedStyle = {
  color: "var(--color-text-muted)",
  fontSize: "11px",
};

const numStyle = {
  fontWeight: 700,
  fontVariantNumeric: "tabular-nums",
  fontSize: "11.5px",
};
