"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

/**
 * LandingNav — N12 "announcement banner + retracting nav". Replaces the
 * previous N9 edge-aligned minimal: N9 is a two-destination nav, and the
 * page now has four real in-page destinations plus the two auth routes,
 * so the empty-space-as-design premise no longer holds.
 *
 * Two tiers in one fixed header:
 *   banner — the MCP launch announcement. Dismissible; dismissal is
 *            remembered in localStorage so it doesn't nag on return.
 *   bar    — wordmark · anchor links · sign in · primary CTA.
 *
 * On scroll-down past 48px the whole header translates up by exactly the
 * banner's height, docking the bar to the top; scroll-up brings the banner
 * back. Per the archetype: translate the header, never animate the banner's
 * height (that janks). Height is only zeroed on dismiss, so the
 * `--banner-h` calc that pads the page reflows with no leftover gap.
 *
 * Banner fill is the archetype's `tint+ink` knob, NOT its default gradient —
 * globals.css's design system bans gradients outright ("No gradients, no
 * glassmorphism, no glow shadows"). A flat indigo tint with accent ink
 * carries the same emphasis inside the house rules.
 */

const NAV_LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#context-layer", label: "Context layer" },
  { href: "#mcp", label: "For agents" },
  { href: "#record", label: "Track record" },
];

const DISMISS_KEY = "fc-mcp-banner-dismissed";

export default function LandingNav() {
  const [compact, setCompact] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const lastY = useRef(0);

  // Read the stored dismissal after mount — reading localStorage during
  // render would break SSR. Returning visitors see one frame of banner
  // before it collapses; that's the right trade vs. every first-time
  // visitor seeing a frame of missing banner.
  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") {
        setDismissed(true);
        document.documentElement.style.setProperty("--banner-h", "0px");
      }
    } catch {
      /* private mode / storage disabled — banner just stays shown */
    }
  }, []);

  useEffect(() => {
    if (dismissed) return undefined;
    const onScroll = () => {
      const y = window.scrollY;
      if (y < 48) setCompact(false);
      else if (y > lastY.current + 2) setCompact(true);
      else if (y < lastY.current - 2) setCompact(false);
      lastY.current = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [dismissed]);

  const dismiss = useCallback(() => {
    setDismissed(true);
    setCompact(false);
    document.documentElement.style.setProperty("--banner-h", "0px");
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* no-op */
    }
  }, []);

  const cls = [
    "landing-header",
    compact ? "is-compact" : "",
    dismissed ? "is-dismissed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <header className={cls}>
      {!dismissed && (
        <div className="landing-banner">
          {/* The long clause is dropped below 48rem so the banner stays
              exactly one line tall at every width — the header translates
              by --banner-h, so a wrapping banner would desync the dock. */}
          <p className="landing-banner__text">
            <span className="landing-banner__tag">New</span>
            FinContext is now an MCP server.
            <span className="landing-banner__long">
              {" "}
              Call it from Claude Desktop, Cursor, or any MCP host.
            </span>
            <a className="landing-banner__link" href="#mcp">
              See the tools →
            </a>
          </p>
          <button
            type="button"
            className="landing-banner__x"
            onClick={dismiss}
            aria-label="Dismiss announcement"
          >
            <svg width="11" height="11" viewBox="0 0 11 11" aria-hidden="true">
              <path
                d="M1 1l9 9M10 1l-9 9"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      )}

      <div className="landing-bar">
        <div className="landing-bar__inner">
          <Link href="/" className="landing-bar__brand">
            <span className="landing-bar__mark">F</span>
            <span className="landing-bar__name">FinContext</span>
          </Link>

          <nav className="landing-bar__links" aria-label="Primary">
            {NAV_LINKS.map((l) => (
              <a key={l.href} href={l.href} className="landing-bar__link">
                {l.label}
              </a>
            ))}
          </nav>

          <div className="landing-bar__actions">
            <Link href="/login" className="landing-bar__signin">
              Sign in
            </Link>
            <Link href="/signup" className="landing-cta-primary landing-bar__cta">
              Start free
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
