"use client";

/**
 * VerifiedStamp — studied DNA from the same reference (a rotated,
 * double-ruled "ticket stamp" card breaking out of the hero's grid).
 * Adapted to a claim the product can actually back up: the outcome
 * ledger. Hand-built Tier A CSS — no asset, no library. Hidden below
 * 60rem (decorative accent, not core content — the same claim is made
 * in full in TrackRecord.jsx, so nothing is lost on mobile).
 */
export default function VerifiedStamp() {
  return (
    <div className="verified-stamp" aria-hidden="true">
      <div className="verified-stamp__inner">
        <span className="verified-stamp__line verified-stamp__line--big">GRADED</span>
        <span className="verified-stamp__line verified-stamp__line--big">IN PUBLIC</span>
        <span className="verified-stamp__rule" />
        <span className="verified-stamp__line verified-stamp__line--small">1D · 5D · 20D</span>
      </div>
    </div>
  );
}
