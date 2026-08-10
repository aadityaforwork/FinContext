"use client";

import Link from "next/link";

/**
 * LandingFooter — Ft1 mast-headed. Replaces the previous Ft2 inline single
 * line: the page now has real destinations worth naming (the agent surface,
 * the public record), and a one-line footer was starting to hide them.
 *
 * Still deliberately NOT Ft3: no four-column Product/Company/Resources/Legal
 * grid, no social-icon row, no tiny copyright tail. A wordmark and tagline
 * anchor the band; two small link clusters sit beside it; the licence and
 * compliance line close it under a hairline.
 */
export default function LandingFooter() {
  return (
    <footer className="landing-footer">
      <div className="landing-footer__inner">
        <div className="landing-footer__mast">
          <div className="landing-footer__brand">
            <span className="landing-footer__mark">F</span>
            <span className="landing-footer__name">FinContext</span>
          </div>
          <p className="landing-footer__tagline">
            Grounded market context for NSE-listed equities — for people, and
            now for their agents.
          </p>
        </div>

        <div className="landing-footer__links">
          <div className="landing-footer__group">
            <p className="landing-footer__group-label">Product</p>
            <Link href="/login">Sign in</Link>
            <Link href="/signup">Start free</Link>
            <Link href="/accuracy">Track record</Link>
          </div>
          <div className="landing-footer__group">
            <p className="landing-footer__group-label">Developers</p>
            <a href="#mcp">MCP tools</a>
            <a href="#context-layer">Context block</a>
          </div>
        </div>
      </div>

      <div className="landing-footer__base">
        <span>© 2026 FinContext</span>
        <span className="landing-footer__note">
          Educational and informational only — not investment advice.
        </span>
      </div>
    </footer>
  );
}
