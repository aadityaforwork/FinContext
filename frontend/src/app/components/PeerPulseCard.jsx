"use client";

/**
 * PeerPulseCard — "Investors with similar sector exposure to yours added
 * these tickers this week." Replaces the old RiskMetricsCard.
 *
 * Compliance shape:
 *   • Surface labels the data as OBSERVATION of peer activity, not advice
 *   • Backend enforces k-anonymity (cohort ≥5, per-ticker adders ≥2) so
 *     no individual user's activity can be inferred
 *   • Disclaimer line at the bottom of the card
 *
 * Editorial-quiet design — same vocabulary as the rest of the product:
 *   - mono caps section label
 *   - hairline-bordered rows, no colored fills
 *   - mono ticker + count chip
 *   - serif italic empties
 */

import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { API_BASE } from "../lib/api";
import { Spinner } from "./Loaders";

const SERIF = "var(--font-serif)";
const MONO  = "var(--font-mono)";

export default function PeerPulseCard({ onTickerClick }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchPulse = async () => {
    if (!user?.id) return;
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/social/peer-pulse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.id }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPulse(); /* eslint-disable-next-line */ }, [user?.id]);

  return (
    <div style={{
      padding: "22px 24px",
      background: "var(--color-bg-card)",
      border: "1px solid var(--border-subtle)",
      borderRadius: "var(--radius-card)",
    }}>
      {/* HEADER */}
      <div style={{
        display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", gap: "12px",
        marginBottom: "16px", flexWrap: "wrap",
      }}>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.3 }}>
          <span style={{
            fontFamily: MONO, fontSize: "10.5px", fontWeight: 700,
            letterSpacing: "0.22em", textTransform: "uppercase",
            color: "var(--color-text-muted)", marginBottom: "6px",
          }}>
            Peer pulse &nbsp;·&nbsp; last 7 days
          </span>
          <h3 style={{
            fontSize: "16px", fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.005em",
            margin: 0,
          }}>
            What investors with sectors like yours are adding
          </h3>
          {data?.cohort_size > 0 && (
            <span style={{
              fontSize: "11.5px", color: "var(--color-text-muted)",
              marginTop: "4px",
            }}>
              Cohort: {data.cohort_size} investor{data.cohort_size === 1 ? "" : "s"} with ≥3 sector overlap
              {data.user_top_sectors?.length > 0 && ` · ${data.user_top_sectors.slice(0, 3).join(" · ")}`}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={fetchPulse}
          disabled={loading}
          aria-label="Refresh peer pulse"
          style={{
            padding: "6px 10px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--border-subtle)",
            background: "transparent",
            color: "var(--color-text-muted)",
            fontFamily: MONO, fontSize: "11px", fontWeight: 700,
            cursor: loading ? "wait" : "pointer",
          }}
        >
          {loading ? <Spinner size="sm" /> : "↻"}
        </button>
      </div>

      {/* BODY */}
      {loading && !data && <LoadingState />}
      {error && !loading && <ErrorState message={error} onRetry={fetchPulse} />}

      {data && !loading && !error && (
        <>
          {!data.available && data.reason === "empty_portfolio" && (
            <EmptyState
              kicker="Add holdings first"
              body="Once you have a few stocks in your portfolio, we can match you to investors with similar sector exposure and show you what they're adding this week."
            />
          )}
          {!data.available && data.reason === "small_cohort" && (
            <EmptyState
              kicker={`Cohort: ${data.cohort_size} of ${data.min_cohort_size} needed`}
              body="Not enough peers with overlapping sectors yet — privacy requires at least 5 similar investors before we surface aggregate activity. Check back as more users join."
            />
          )}
          {!data.available && (data.reason === "service_unconfigured" || data.reason === "fetch_failed") && (
            <EmptyState
              kicker="Service temporarily unavailable"
              body="Peer pulse couldn't load right now. Try refreshing in a moment."
            />
          )}

          {data.available && data.items.length === 0 && (
            <EmptyState
              kicker="Quiet week"
              body={`No new ticker activity from your peer cohort in the last ${data.lookback_days} days.`}
            />
          )}

          {data.available && data.items.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column" }}>
              {data.items.map((item, i) => (
                <PulseRow
                  key={item.ticker}
                  item={item}
                  rank={i + 1}
                  onClick={() => onTickerClick?.(item.ticker)}
                  last={i === data.items.length - 1}
                />
              ))}
            </ul>
          )}

          {data?.disclaimer_short && (
            <p style={{
              fontSize: "10.5px", color: "var(--color-text-muted)",
              marginTop: "16px", paddingTop: "12px",
              borderTop: "1px solid var(--border-subtle)",
              fontFamily: SERIF, fontStyle: "italic",
              lineHeight: 1.5,
            }}>
              {data.disclaimer_short}
            </p>
          )}
          <p style={{
            fontSize: "10.5px", color: "var(--color-text-muted)",
            marginTop: "8px",
            fontFamily: SERIF, fontStyle: "italic",
            lineHeight: 1.5,
          }}>
            This is an observation of aggregate peer activity, not a recommendation.
            Counts are k-anonymous (minimum two adders per ticker).
          </p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function PulseRow({ item, rank, onClick, last }) {
  // Bar width is scaled to the most-added item (which is always rank #1 with
  // the highest adders count). Computed by parent — for now use adders_pct
  // capped at a sane max so the bar doesn't look 100% on small cohorts.
  const pct = Math.min(100, item.adders_pct);
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        style={{
          width: "100%",
          display: "grid",
          gridTemplateColumns: "26px 1fr auto",
          alignItems: "center",
          gap: "12px",
          padding: "12px 8px",
          background: "transparent",
          border: "none",
          borderBottom: last ? "none" : "1px dashed var(--border-subtle)",
          cursor: "pointer",
          textAlign: "left",
          transition: "background 0.15s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-card-hover, rgba(255,255,255,0.03))")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <span style={{
          fontFamily: MONO, fontSize: "10.5px", fontWeight: 700,
          color: "var(--color-text-muted)", letterSpacing: "0.05em",
        }}>
          {String(rank).padStart(2, "0")}
        </span>

        <div style={{ display: "flex", flexDirection: "column", gap: "4px", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px", flexWrap: "wrap" }}>
            <span style={{
              fontFamily: MONO, fontSize: "13.5px", fontWeight: 800,
              color: "var(--color-text-primary)", letterSpacing: "0.01em",
            }}>
              {item.ticker}
            </span>
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {item.name}
            </span>
            <span style={{
              padding: "1px 7px",
              fontFamily: MONO, fontSize: "9.5px", fontWeight: 700,
              color: "var(--color-text-muted)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "4px",
              textTransform: "uppercase", letterSpacing: "0.12em",
            }}>
              {item.sector}
            </span>
          </div>
          {/* Tiny proportion bar — quiet hint of intensity, no fill color */}
          <div style={{
            height: "2px", width: "100%",
            background: "rgba(255,255,255,0.05)",
            borderRadius: "2px",
          }}>
            <div style={{
              height: "100%", width: `${pct}%`,
              background: "var(--color-accent-primary)",
              opacity: 0.5, borderRadius: "2px",
              transition: "width 0.6s cubic-bezier(0.4, 0, 0.2, 1)",
            }} />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "1px" }}>
          <span style={{
            fontFamily: MONO, fontSize: "13px", fontWeight: 700,
            color: "var(--color-accent-primary)",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: "0.01em",
          }}>
            {item.adders}
            <span style={{ fontSize: "10px", color: "var(--color-text-muted)", marginLeft: "3px" }}>added</span>
          </span>
          <span style={{
            fontFamily: MONO, fontSize: "9.5px", color: "var(--color-text-muted)",
            letterSpacing: "0.04em", fontVariantNumeric: "tabular-nums",
          }}>
            {item.portfolio_adds > 0 && `${item.portfolio_adds} bought`}
            {item.portfolio_adds > 0 && item.watchlist_adds > 0 && " · "}
            {item.watchlist_adds > 0 && `${item.watchlist_adds} watched`}
          </span>
        </div>
      </button>
    </li>
  );
}

function EmptyState({ kicker, body }) {
  return (
    <div style={{
      padding: "32px 20px",
      textAlign: "center",
      border: "1px dashed var(--border-subtle)",
      borderRadius: "var(--radius-card)",
    }}>
      <div style={{
        fontFamily: MONO, fontSize: "10px", fontWeight: 700,
        letterSpacing: "0.22em", textTransform: "uppercase",
        color: "var(--color-text-muted)", marginBottom: "12px",
      }}>
        {kicker}
      </div>
      <p style={{
        fontFamily: SERIF, fontStyle: "italic",
        fontSize: "14px", color: "var(--color-text-secondary)",
        margin: 0, lineHeight: 1.55, maxWidth: "440px",
        marginInline: "auto",
        letterSpacing: "-0.003em",
      }}>
        {body}
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div style={{
      padding: "40px 20px",
      display: "flex", flexDirection: "column",
      alignItems: "center", gap: "12px",
    }}>
      <Spinner size="sm" />
      <span style={{
        fontFamily: MONO, fontSize: "10.5px", fontWeight: 700,
        letterSpacing: "0.18em", textTransform: "uppercase",
        color: "var(--color-text-muted)",
      }}>
        Matching your cohort…
      </span>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div style={{ padding: "20px", textAlign: "center" }}>
      <div style={{
        fontFamily: MONO, fontSize: "10.5px", fontWeight: 700,
        letterSpacing: "0.16em", textTransform: "uppercase",
        color: "var(--color-accent-red)", marginBottom: "8px",
      }}>
        Peer pulse failed
      </div>
      <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "14px" }}>
        {message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        style={{
          padding: "6px 14px",
          borderRadius: "var(--radius-control)",
          border: "1px solid var(--color-accent-red)",
          background: "transparent",
          color: "var(--color-accent-red)",
          fontFamily: MONO, fontSize: "11px", fontWeight: 700,
          letterSpacing: "0.06em", textTransform: "uppercase",
          cursor: "pointer",
        }}
      >
        Retry
      </button>
    </div>
  );
}
