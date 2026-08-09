"use client";

/**
 * SignalCard — fills the empty right-hand column beside the headline.
 * Not a screenshot (this route has no real product capture to show
 * honestly) and not a real market claim — a clearly-labelled illustrative
 * sample of the *shape* of a grounded explanation: a move, a cited
 * catalyst, a confidence rating. Every number here is fictional and
 * marked as such, twice (label at top, note at bottom), so it can't be
 * mistaken for a live figure or investment signal.
 */
export default function SignalCard() {
  return (
    <div className="signal-card">
      <p className="signal-card__eyebrow">Illustrative example · not real data</p>

      <div className="signal-card__row">
        <span className="signal-card__ticker">SAMPLE · IT SERVICES</span>
        <span className="signal-card__change">+2.4%</span>
      </div>

      <p className="signal-card__narrative">
        Sector-wide move — IT services names rallied on stronger-than-expected
        US tech earnings overnight.
      </p>

      <div className="signal-card__cite">
        <span className="signal-card__cite-dot" aria-hidden="true" />
        source: sector news, overnight
      </div>

      <div className="signal-card__confidence">
        <span className="signal-card__confidence-label">Confidence</span>
        <span className="signal-card__confidence-bar" aria-hidden="true">
          <span className="signal-card__confidence-seg signal-card__confidence-seg--on" />
          <span className="signal-card__confidence-seg signal-card__confidence-seg--on" />
          <span className="signal-card__confidence-seg" />
        </span>
        <span className="signal-card__confidence-value">Medium</span>
      </div>

      <p className="signal-card__note">
        A sample of the shape of an explanation, not a live figure.
      </p>
    </div>
  );
}
