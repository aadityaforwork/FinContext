"use client";

import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";

/**
 * Plain-English explanations for the technical concepts that show up across
 * the dashboard. Surfaced via <Hint> wherever a Pill / Metric / badge is rendered.
 */
export const TECH_TOOLTIPS = {
  rsi:           "Relative Strength Index (14-day). A momentum gauge from 0 to 100. Above 70 = overbought (price stretched, may pause or pull back). Below 30 = oversold (may bounce). 40–60 is the neutral middle.",
  vol_vs_avg:    "Today's traded volume divided by the 20-day average. Above 1.4× = high conviction behind the move. Below 0.6× = quiet — a price move on weak volume may not stick.",
  momentum_5d:   "Price change over the last 5 trading days. Short-term trend direction.",
  momentum_20d:  "Price change over the last 20 trading days. Slower-moving trend. When 5d and 20d agree, the trend is strong. When they disagree, the trend may be reversing.",
  momentum_state:"Combined read of 5d and 20d momentum. 'extending_up' = both positive and accelerating. 'reversing_*' = the two are pulling in opposite directions.",
  vs_sma20:      "Distance from the 20-day simple moving average. Price above = short-term uptrend. Below = short-term downtrend.",
  vs_sma50:      "Distance from the 50-day simple moving average — a common medium-term trend benchmark. Sustained above SMA50 is typical of healthy uptrends.",
  sma_state:     "Whether the current price sits above or below the 50-day moving average. The single quickest read of medium-term trend direction.",
  from_20d_high: "How far below the highest close of the last 20 trading days. 0% = at the high (resistance). −5% leaves room before a fresh high.",
  from_20d_low:  "How far above the lowest close of the last 20 trading days. 0% = at the low (support). Larger positive numbers mean more cushion above support.",
  conviction:    "How many independent signals agree with this call (news + technicals + sector move + FII/DII flow). Capped at 95 — markets are never certain. Below 50 is hidden. 50–69 = directional but soft. 70+ = multiple signals agree.",
};

const TOOLTIP_WIDTH = 260;
const TOOLTIP_OFFSET = 6;
const VIEWPORT_PADDING = 8;
const TOOLTIP_HEIGHT_ESTIMATE = 90;

/**
 * Hint — wraps a label/pill and reveals a styled tooltip on hover/focus.
 *
 * The tooltip is rendered via createPortal to document.body using
 * `position: fixed` so it can never overflow its parent's scroll container
 * (modals, grids, etc.). Position auto-flips when near the viewport edges:
 *
 *   • Default placement is below the trigger, aligned to its left edge.
 *   • Near right edge → right-aligned to the trigger's right edge.
 *   • Near bottom edge → placed above the trigger.
 *
 * Props:
 *   text     — tooltip body (skipped if falsy; the wrapper renders children as-is)
 *   showIcon — if true, renders a small ⓘ next to the child so the hover
 *              affordance is discoverable (use for plain-text labels).
 */
export function Hint({ text, children, showIcon = false }) {
  const triggerRef = useRef(null);
  const [pos, setPos] = useState(null); // null = closed; {top, left} = open

  const open = () => {
    const r = triggerRef.current?.getBoundingClientRect();
    if (!r) return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Horizontal: default left-align to trigger; flip to right-align if it
    // would overflow the viewport right edge; clamp to padding on either side.
    let left = r.left;
    if (left + TOOLTIP_WIDTH > vw - VIEWPORT_PADDING) {
      left = Math.max(VIEWPORT_PADDING, r.right - TOOLTIP_WIDTH);
    }
    if (left < VIEWPORT_PADDING) left = VIEWPORT_PADDING;

    // Vertical: default below; flip above if it would overflow the bottom.
    let top = r.bottom + TOOLTIP_OFFSET;
    if (top + TOOLTIP_HEIGHT_ESTIMATE > vh - VIEWPORT_PADDING) {
      top = Math.max(VIEWPORT_PADDING, r.top - TOOLTIP_OFFSET - TOOLTIP_HEIGHT_ESTIMATE);
    }

    setPos({ top, left });
  };

  const close = () => setPos(null);

  // Auto-close on scroll — if the user scrolls the modal (or page) the
  // trigger's position changes but the tooltip is fixed; hide it so we don't
  // show a floating tooltip detached from its trigger.
  useEffect(() => {
    if (!pos) return;
    const onScroll = () => setPos(null);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [pos]);

  if (!text) return children;

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={open}
        onMouseLeave={close}
        onFocus={open}
        onBlur={close}
        style={{
          position: "relative",
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          cursor: "help",
        }}
      >
        {children}
        {showIcon && (
          <span aria-hidden style={{
            fontSize: "10px", color: "var(--color-text-muted)",
            opacity: 0.6, lineHeight: 1,
          }}>ⓘ</span>
        )}
      </span>
      {pos && typeof document !== "undefined" && createPortal(
        <div
          role="tooltip"
          style={{
            position: "fixed",
            top: `${pos.top}px`,
            left: `${pos.left}px`,
            width: `${TOOLTIP_WIDTH}px`,
            padding: "8px 10px",
            background: "#0c0a13",
            border: "1px solid #2a2542",
            borderRadius: "8px",
            fontSize: "11px",
            lineHeight: 1.5,
            color: "var(--color-text-secondary)",
            textTransform: "none",
            letterSpacing: "0.01em",
            fontWeight: 400,
            zIndex: 10000,
            pointerEvents: "none",
            boxShadow: "0 6px 24px rgba(0,0,0,0.5)",
            whiteSpace: "normal",
          }}
        >
          {text}
        </div>,
        document.body,
      )}
    </>
  );
}
