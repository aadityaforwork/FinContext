"use client";

import { useState, useCallback, useMemo } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useCache } from "../lib/useCache";
import { Spinner } from "./Loaders";
import NewsWireLoader from "./NewsWireLoader";
import Modal from "./Modal";
import { Hint, TECH_TOOLTIPS } from "./Tooltips";
import {
  SignalIcon, RefreshIcon, CompanyIcon, SectorIcon, MacroIcon, GlobalIcon,
} from "./Icons";
import { Reveal } from "./AnimatedNumber";
import YourStake from "./YourStake";

/**
 * NewsImpactFeed — premium edition
 * ---------------------------------
 * Compact rows. Restrained color. Information-dense. Each row ~88px.
 * Internally scrollable so the surrounding page never grows.
 */

const IMPACT = {
  high:   { color: "#ef4444", label: "HIGH" },
  medium: { color: "#f59e0b", label: "MED"  },
  low:    { color: "#94a3b8", label: "LOW"  },
};

const DIRECTION = {
  positive: { color: "var(--color-accent-green)", arrow: "▲" },
  negative: { color: "var(--color-accent-red)",   arrow: "▼" },
  mixed:    { color: "var(--color-accent-amber)", arrow: "◆" },
};

// SVG category glyphs replace the old emoji map (📌🏭🇮🇳🌍).
const CATEGORY_GLYPH = {
  stock_specific: CompanyIcon,
  sector: SectorIcon,
  macro: MacroIcon,
  global: GlobalIcon,
};

function CatGlyph({ category, size = 13 }) {
  const G = CATEGORY_GLYPH[category] || MacroIcon;
  return (
    <span style={{ display: "flex", color: "var(--color-text-muted)" }}>
      <G size={size} />
    </span>
  );
}

const CATEGORY_LABEL = {
  stock_specific: "Company news",
  sector: "Sector",
  macro: "India macro",
  global: "Global",
};

const RSI_COLORS = {
  oversold:   "#10b981",
  weak:       "#84cc16",
  neutral:    "#64748b",
  strong:     "#f59e0b",
  overbought: "#ef4444",
};

const VOL_COLORS = {
  low:    "#64748b",
  normal: "#64748b",
  high:   "#f59e0b",
  surge:  "#ef4444",
};

function NewsRow({ item, onTickerClick, onOpen, holdingsToday }) {
  const dot = IMPACT[item.impact_level] || IMPACT.low;
  const dir = DIRECTION[item.direction] || DIRECTION.mixed;
  const isPolicy = (item.scope || "").startsWith("policy_");
  const policyLabel = item.scope === "policy_rbi" ? "RBI" : "POLICY";

  return (
    <div
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onClick={onOpen}
      onKeyDown={(e) => { if (onOpen && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onOpen(); } }}
      className={onOpen ? "living-row" : undefined}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: "12px",
        padding: "12px 14px",
        background: "transparent",
        borderRadius: "10px",
        border: "1px solid var(--border-subtle)",
        cursor: onOpen ? "pointer" : "default",
        transition: "transform 0.16s ease, border-color 0.15s, background 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(99,102,241,0.04)";
        e.currentTarget.style.borderColor = "rgba(99,102,241,0.20)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.borderColor = "var(--border-subtle)";
      }}
    >
      {/* Left rail: impact dot + direction arrow */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "4px",
          paddingTop: "2px",
          minWidth: "16px",
        }}
      >
        <span
          title={`${dot.label} impact`}
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: dot.color,
          }}
        />
        <span style={{ color: dir.color, fontSize: "9px", fontWeight: 700 }}>{dir.arrow}</span>
      </div>

      {/* Right: content */}
      <div style={{ minWidth: 0 }}>
        {/* META — single line */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginBottom: "4px",
            fontSize: "10px",
            color: "var(--color-text-muted)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          <CatGlyph category={item.category} size={12} />
          <span>{dot.label}</span>
          {isPolicy && (
            <>
              <span style={{ opacity: 0.5 }}>·</span>
              <span
                title={item.scope === "policy_rbi"
                  ? "RBI press release / notification"
                  : "Government press release (PIB)"}
                style={{
                  padding: "1px 6px",
                  borderRadius: "4px",
                  background: "rgba(245,158,11,0.16)",
                  color: "var(--color-accent-amber)",
                  border: "1px solid rgba(245,158,11,0.35)",
                  fontSize: "9px",
                  fontWeight: 800,
                  letterSpacing: "0.06em",
                }}
              >
                {policyLabel}
              </span>
            </>
          )}
          {item.conviction != null && (
            <>
              <span style={{ opacity: 0.5 }}>·</span>
              <ConvictionChip conviction={item.conviction} />
            </>
          )}
          {item.source && (
            <>
              <span style={{ opacity: 0.5 }}>·</span>
              <span style={{ textTransform: "none", fontStyle: "italic", color: "var(--color-text-muted)" }}>
                {item.source}
              </span>
            </>
          )}
        </div>

        {/* HEADLINE */}
        <p
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--color-text-primary)",
            lineHeight: 1.4,
            marginBottom: "6px",
          }}
        >
          {item.headline}
        </p>

        {/* AFFECTED + WHY */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: "4px", flexShrink: 0 }}>
            {(item.affected_tickers || []).slice(0, 3).map((t) => (
              <button
                key={t}
                type="button"
                onClick={(e) => { e.stopPropagation(); onTickerClick?.(t); }}
                style={{
                  padding: "1px 6px",
                  borderRadius: "4px",
                  background: "rgba(99,102,241,0.10)",
                  color: "var(--color-accent-secondary)",
                  border: "1px solid rgba(99,102,241,0.20)",
                  fontSize: "10px",
                  fontFamily: "var(--font-mono)",
                  fontWeight: 700,
                  cursor: "pointer",
                  letterSpacing: "0.02em",
                }}
              >
                {t}
              </button>
            ))}
          </div>
          {item.reason && (
            <p
              style={{
                fontSize: "11.5px",
                color: "var(--color-text-secondary)",
                lineHeight: 1.4,
                margin: 0,
                flex: "1 1 220px",
                minWidth: 0,
              }}
            >
              <span style={{ color: "var(--color-text-muted)" }}>Why: </span>
              {item.reason}
            </p>
          )}
        </div>

        {/* Sector chips for policy items — gives the user immediate context
            on which slice of the economy a PIB/RBI release touches, even
            before they parse the headline. */}
        {item.affected_sectors?.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "6px" }}>
            {item.affected_sectors.slice(0, 4).map((s) => (
              <span
                key={s}
                style={{
                  padding: "1px 6px",
                  borderRadius: "4px",
                  background: "rgba(6,182,212,0.10)",
                  color: "var(--color-accent-cyan)",
                  border: "1px solid rgba(6,182,212,0.22)",
                  fontSize: "9.5px",
                  fontWeight: 700,
                  letterSpacing: "0.02em",
                }}
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {item.technical_context && (
          <p
            style={{
              fontSize: "10.5px",
              color: "var(--color-text-muted)",
              lineHeight: 1.35,
              margin: "6px 0 0 0",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.01em",
            }}
          >
            <span style={{ color: "#a855f7", fontWeight: 700, marginRight: "4px" }}>TA</span>
            {item.technical_context}
          </p>
        )}

        {/* Your stake — answers "what does this mean for ME?" Sums across all
            affected tickers the user actually holds. Hidden silently if zero
            overlap, so non-portfolio sector news doesn't get noisy. */}
        <YourStake
          tickers={item.affected_tickers}
          holdingsToday={holdingsToday}
          variant="news"
        />
      </div>
    </div>
  );
}

export default function NewsImpactFeed({ onNavigate }) {
  const { user } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState("all");
  const [activeItem, setActiveItem] = useState(null); // click-through detail modal

  // The actual fetch — supabase reads + POST to news-feed.
  // `force` is forwarded to the backend so the user-clicked refresh button
  // bypasses the SWR window and recomputes; localStorage is overwritten either way.
  const fetchFeed = useCallback(async (force = false) => {
    if (!user?.id) throw new Error("Not signed in");
    const [{ data: positions }, { data: watchRows }] = await Promise.all([
      supabase.from("portfolio").select("ticker, quantity, buy_price").eq("user_id", user.id),
      supabase.from("watchlist").select("ticker").eq("user_id", user.id),
    ]);
    const res = await fetch(`${API_BASE}/api/intelligence/news-feed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        positions: positions || [],
        watchlist_tickers: (watchRows || []).map((r) => r.ticker),
        force_refresh: force,
      }),
    });
    if (!res.ok) throw new Error(`Feed request failed (${res.status})`);
    return await res.json();
  }, [user?.id]);

  // Cache by user.id with a 30-min local window — second-visit-onwards is instant.
  // Background refresh keeps it fresh; portfolio changes within the window
  // surface on the next refresh (manual button or after window expires).
  // The fetchFn forwards a `force` arg the hook passes through from refresh().
  const {
    data: feed,
    loading,
    stale,
    error: fetchError,
    refresh,
  } = useCache(`news-feed:${user?.id || "anon"}`, fetchFeed, {
    enabled: !!user?.id,
    maxAgeMs: 30 * 60 * 1000,
  });

  // Surface either a fetch error OR a payload-level error from the backend.
  const error = fetchError || feed?.error || null;

  const items = useMemo(() => {
    const all = feed?.items || [];
    if (filter === "high") return all.filter((i) => i.impact_level === "high");
    return all;
  }, [feed, filter]);

  const handleTickerClick = (t) => onNavigate?.("company", t);

  const onRefreshClick = async () => {
    setRefreshing(true);
    try {
      // refresh(silent=true, force=true) keeps current items on screen while
      // the new payload arrives, and forwards force=true to fetchFn so the
      // backend SWR window is bypassed.
      await refresh(true, true);
    } catch {
      // Errors land in fetchError via useCache.
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div
      data-tour="news-feed"
      className="dash-news-feed"
      style={{
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "12px",
        padding: "14px 16px 16px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* HEADER */}
      <div
        className="dnf-header"
        style={{
          paddingBottom: "12px",
          marginBottom: "10px",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2
            style={{
              fontSize: "13px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              letterSpacing: "-0.01em",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span style={{ display: "flex", color: "var(--color-accent-primary)" }}>
              <SignalIcon size={15} />
            </span>
            News hitting your portfolio
          </h2>
          <p style={{ fontSize: "10px", color: "var(--color-text-muted)", marginTop: "3px", letterSpacing: "0.02em" }}>
            {feed?.demo_mode
              ? "Sample feed — add holdings for live personalization"
              : (
                <>
                  {items.length} high-conviction {items.length === 1 ? "item" : "items"}
                  {feed?.hidden_low_conviction_count > 0 && (
                    <> · {feed.hidden_low_conviction_count} hidden where signals didn't agree</>
                  )}
                </>
              )}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div
            style={{
              display: "flex",
              border: "1px solid var(--border-subtle)",
              borderRadius: "6px",
              overflow: "hidden",
            }}
          >
            {[
              { id: "all",  label: "All"  },
              { id: "high", label: "High" },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                style={{
                  padding: "5px 10px",
                  fontSize: "10px",
                  fontWeight: 700,
                  border: "none",
                  background: filter === f.id ? "rgba(99,102,241,0.12)" : "transparent",
                  color: filter === f.id ? "var(--color-accent-secondary)" : "var(--color-text-muted)",
                  cursor: "pointer",
                  letterSpacing: "0.02em",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          {(stale || refreshing) && (
            <span
              title={refreshing ? "Refreshing live data…" : "Showing cached — refreshing"}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                padding: "3px 7px",
                borderRadius: "9999px",
                background: "rgba(99,102,241,0.10)",
                border: "1px solid rgba(99,102,241,0.22)",
                fontSize: "9px",
                fontWeight: 700,
                color: "var(--color-accent-secondary)",
                letterSpacing: "0.04em",
                textTransform: "uppercase",
              }}
            >
              <span
                className="pulse-dot"
                style={{
                  width: "5px",
                  height: "5px",
                  borderRadius: "50%",
                  background: "var(--color-accent-secondary)",
                }}
              />
              Live
            </span>
          )}
          <button
            type="button"
            onClick={onRefreshClick}
            disabled={refreshing}
            aria-label="Refresh"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "28px",
              height: "26px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--border-subtle)",
              background: "var(--color-bg-card)",
              color: "var(--color-text-muted)",
              cursor: refreshing ? "wait" : "pointer",
              opacity: refreshing ? 0.6 : 1,
            }}
          >
            {refreshing ? <Spinner size="sm" /> : <RefreshIcon size={13} />}
          </button>
        </div>
      </div>

      {/* BODY */}
      <div style={{ flex: 1, overflowY: "auto", paddingRight: "4px" }}>
        {loading ? (
          <NewsWireLoader />
        ) : items.length === 0 ? (
          <div
            style={{
              padding: "40px 16px",
              textAlign: "center",
              color: "var(--color-text-muted)",
              fontSize: "12px",
            }}
          >
            {error ? (
              <>
                <p style={{ marginBottom: "10px" }}>{error}</p>
                <button
                  type="button"
                  onClick={onRefreshClick}
                  style={{
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "none",
                    background: "rgba(99,102,241,0.15)",
                    color: "var(--color-accent-secondary)",
                    fontSize: "11px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Try again
                </button>
              </>
            ) : (
              <>
                <span style={{ fontSize: "22px", display: "block", marginBottom: "6px" }}>🌤️</span>
                {filter === "high"
                  ? "No high-impact items right now."
                  : "Markets are quiet on your universe."}
              </>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {items.map((item, i) => (
              <Reveal key={item.news_id || i} index={i} step={32}>
                <NewsRow
                  item={item}
                  onTickerClick={handleTickerClick}
                  onOpen={() => setActiveItem(item)}
                  holdingsToday={feed?.holdings_today}
                />
              </Reveal>
            ))}
          </div>
        )}
      </div>

      {activeItem && (
        <NewsDetailModal
          item={activeItem}
          allItems={feed?.items || []}
          universeTechnicals={feed?.universe_technicals || {}}
          onClose={() => setActiveItem(null)}
          onOpen={(it) => setActiveItem(it)}
          onTickerClick={handleTickerClick}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NewsDetailModal — full reasoning view for one news item. Surfaces the data
// the LLM used: each affected ticker's current technical state, the semantic
// similarity score (if it was a pgvector hit, not a literal-name match), the
// full snippet, and a direct link to the source.
// ---------------------------------------------------------------------------
function NewsDetailModal({ item, allItems = [], universeTechnicals, onClose, onOpen, onTickerClick }) {
  const dot = IMPACT[item.impact_level] || IMPACT.low;
  const dir = DIRECTION[item.direction] || DIRECTION.mixed;
  const catLabel = CATEGORY_LABEL[item.category] || item.category;
  const affected = item.affected_tickers || [];
  const isSemantic = item.semantic_similarity != null;

  // Find other items in the same feed that touch any of the same tickers.
  // Sorted by impact (high first) so the most relevant coverage shows up top.
  // Capped at 4 to keep the modal scannable.
  const affectedSet = new Set(affected);
  const impactRank = { high: 0, medium: 1, low: 2 };
  const related = (allItems || [])
    .filter((it) => it.news_id !== item.news_id
                 && (it.affected_tickers || []).some((t) => affectedSet.has(t)))
    .sort((a, b) => (impactRank[a.impact_level] ?? 3) - (impactRank[b.impact_level] ?? 3))
    .slice(0, 4);

  const header = (
    <div style={{ minWidth: 0 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap",
        fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
        textTransform: "uppercase", letterSpacing: "0.04em",
      }}>
        <CatGlyph category={item.category} size={13} />
        <span>{catLabel}</span>
        <span style={{ color: dot.color }}>· {dot.label}</span>
        <span style={{ color: dir.color }}>· {dir.arrow} {item.direction}</span>
        {item.source && <span style={{ textTransform: "none", fontStyle: "italic" }}>· {item.source}</span>}
      </div>
      <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", margin: "8px 0 0 0", lineHeight: 1.4 }}>
        {item.headline}
      </h3>
      {item.url && (
        <a href={item.url} target="_blank" rel="noopener noreferrer" style={{
          display: "inline-block", marginTop: "8px",
          fontSize: "11px", color: "var(--color-accent-secondary)",
          textDecoration: "none", fontWeight: 600,
        }}>
          Open source ↗
        </a>
      )}
    </div>
  );

  return (
    <Modal onClose={onClose} header={header}>
        {/* Why — the LLM's transmission-mechanism reason */}
        {item.reason && (
          <NewsModalSection title="Why this matters">
            <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0 }}>
              {item.reason}
            </p>
          </NewsModalSection>
        )}

        {/* Snippet from the source */}
        {item.snippet && (
          <NewsModalSection title="From the source">
            <p style={{ fontSize: "12px", color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0, fontStyle: "italic" }}>
              "{item.snippet}"
            </p>
          </NewsModalSection>
        )}

        {/* Semantic match details */}
        {isSemantic && (
          <NewsModalSection
            title="How we linked this"
            hint="pgvector embedded the headline and matched it against your holdings — the score below shows how close the meaning is, not the keyword overlap."
          >
            <div style={{
              display: "flex", alignItems: "center", gap: "10px",
              padding: "10px 12px", background: "rgba(168,85,247,0.08)",
              border: "1px solid rgba(168,85,247,0.25)", borderRadius: "8px",
            }}>
              <span style={{
                padding: "3px 8px", borderRadius: "6px",
                fontSize: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px",
                background: "rgba(168,85,247,0.18)", color: "#a855f7",
              }}>
                Semantic match
              </span>
              {item.semantic_match_ticker && (
                <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
                  → <span style={{ fontWeight: 700, color: "var(--color-text-primary)" }}>{item.semantic_match_ticker}</span>
                </span>
              )}
              <span style={{ fontSize: "12px", color: "var(--color-text-muted)", marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>
                cosine similarity <span style={{ color: "#a855f7", fontWeight: 700 }}>{item.semantic_similarity}</span>
              </span>
            </div>
          </NewsModalSection>
        )}

        {/* Per-ticker technical state — one card per affected holding */}
        {affected.length > 0 && (
          <NewsModalSection
            title={`Affected holdings (${affected.length})`}
            hint="Click a ticker to open its company page."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {affected.map((t) => (
                <TickerTechCard
                  key={t}
                  ticker={t}
                  tech={universeTechnicals?.[t]}
                  onClick={() => onTickerClick?.(t)}
                />
              ))}
            </div>
          </NewsModalSection>
        )}

        {related.length > 0 && (
          <NewsModalSection
            title={`Related coverage (${related.length})`}
            hint="Other news in your feed that touches the same holdings — click to open."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {related.map((r) => (
                <RelatedNewsRow
                  key={r.news_id}
                  item={r}
                  onClick={() => onOpen?.(r)}
                />
              ))}
            </div>
          </NewsModalSection>
        )}
    </Modal>
  );
}

function RelatedNewsRow({ item, onClick }) {
  const dot = IMPACT[item.impact_level] || IMPACT.low;
  const dir = DIRECTION[item.direction] || DIRECTION.mixed;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick?.(); } }}
      style={{
        padding: "10px 12px", borderRadius: "8px",
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border-subtle)",
        cursor: "pointer",
        transition: "background 0.15s, border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(99,102,241,0.05)";
        e.currentTarget.style.borderColor = "rgba(99,102,241,0.25)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.02)";
        e.currentTarget.style.borderColor = "var(--border-subtle)";
      }}
    >
      <div style={{
        display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap",
        fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
        textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "4px",
      }}>
        <span style={{ color: dot.color }}>{dot.label}</span>
        <span style={{ color: dir.color }}>· {dir.arrow} {item.direction}</span>
        {item.source && <span style={{ textTransform: "none", fontStyle: "italic" }}>· {item.source}</span>}
      </div>
      <div style={{ fontSize: "12px", color: "var(--color-text-primary)", fontWeight: 600, lineHeight: 1.4 }}>
        {item.headline}
      </div>
      <div style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "4px" }}>
        {(item.affected_tickers || []).slice(0, 4).map((t) => (
          <span key={t} style={{
            padding: "1px 6px", borderRadius: "4px",
            background: "rgba(99,102,241,0.10)", color: "var(--color-accent-secondary)",
            fontSize: "10px", fontWeight: 700,
            fontFamily: "var(--font-mono)",
          }}>{t}</span>
        ))}
      </div>
    </div>
  );
}

function NewsModalSection({ title, hint, children }) {
  return (
    <div style={{ marginTop: "18px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "8px" }}>
        <span style={{
          fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
          textTransform: "uppercase", letterSpacing: "1.2px",
        }}>{title}</span>
      </div>
      {hint && (
        <p style={{ fontSize: "11px", color: "var(--color-text-muted)", fontStyle: "italic", margin: "-4px 0 8px 0", lineHeight: 1.5 }}>
          {hint}
        </p>
      )}
      {children}
    </div>
  );
}

function TickerTechCard({ ticker, tech, onClick }) {
  const has = tech && (tech.rsi_zone || tech.vol_zone || tech.momentum_state || tech.sma_state);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick?.(); } }}
      style={{
        padding: "10px 12px", borderRadius: "8px",
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border-subtle)",
        cursor: "pointer",
        transition: "background 0.15s, border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(99,102,241,0.05)";
        e.currentTarget.style.borderColor = "rgba(99,102,241,0.25)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.02)";
        e.currentTarget.style.borderColor = "var(--border-subtle)";
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <span style={{
          fontSize: "13px", fontWeight: 800, color: "var(--color-text-primary)",
          fontFamily: "var(--font-mono)",
        }}>
          {ticker}
        </span>
        {has ? (
          <>
            {tech.rsi_zone && <TechPill color={RSI_COLORS[tech.rsi_zone] || "#64748b"} label={`RSI ${tech.rsi_zone}`} tooltip={TECH_TOOLTIPS.rsi} />}
            {tech.vol_zone && <TechPill color={VOL_COLORS[tech.vol_zone] || "#64748b"} label={`Vol ${tech.vol_zone}`} tooltip={TECH_TOOLTIPS.vol_vs_avg} />}
            {tech.momentum_state && <TechPill color="#a855f7" label={tech.momentum_state.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.momentum_state} />}
            {tech.sma_state && <TechPill color="#06b6d4" label={tech.sma_state.replace(/_/g, " ")} tooltip={TECH_TOOLTIPS.sma_state} />}
            {tech.pct_from_20d_high != null && (
              <span style={{ fontSize: "10px", color: "var(--color-text-muted)", marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>
                {tech.pct_from_20d_high}% from 20d high
              </span>
            )}
          </>
        ) : (
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)", fontStyle: "italic" }}>
            No technical data
          </span>
        )}
      </div>
    </div>
  );
}

function TechPill({ color, label, tooltip }) {
  const pill = (
    <span style={{
      padding: "2px 7px", borderRadius: "5px",
      fontSize: "9.5px", fontWeight: 700,
      background: `${color}20`, color,
      textTransform: "uppercase", letterSpacing: "0.4px",
      cursor: tooltip ? "help" : "default",
    }}>
      {label}
    </span>
  );
  return tooltip ? <Hint text={tooltip}>{pill}</Hint> : pill;
}

function ConvictionChip({ conviction }) {
  if (conviction == null) return null;
  const color = conviction >= 70 ? "var(--color-accent-green)" : conviction >= 50 ? "#f59e0b" : "#94a3b8";
  const chip = (
    <span style={{
      padding: "1px 6px", borderRadius: "4px",
      background: `${color}1f`, color,
      fontSize: "10px", fontWeight: 700, fontVariantNumeric: "tabular-nums",
      letterSpacing: "0.02em", cursor: "help",
    }}>
      ⚡ {conviction}%
    </span>
  );
  return <Hint text={TECH_TOOLTIPS.conviction}>{chip}</Hint>;
}
