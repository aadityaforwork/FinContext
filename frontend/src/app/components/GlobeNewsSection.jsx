"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  Line,
} from "react-simple-maps";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

// ISO-3166-1 numeric → our country codes
const COUNTRY_MAP = {
  "356": "IN", "840": "US", "156": "CN", "392": "JP",
  "826": "GB", "682": "SA", "643": "RU",
  "250": "EU", "276": "EU", "380": "EU", "724": "EU",
  "528": "EU", "056": "EU", "040": "EU", "620": "EU",
  "300": "EU", "246": "EU", "372": "EU",
};

const COUNTRY_INFO = {
  IN: { name: "India",          flag: "🇮🇳", coords: [78.96, 20.59],  index: "NIFTY 50",    tz: "Asia/Kolkata",     marketOpen: 9.25, marketClose: 15.5 },
  US: { name: "United States",  flag: "🇺🇸", coords: [-95.71, 37.09], index: "S&P 500",     tz: "America/New_York", marketOpen: 9.5,  marketClose: 16   },
  CN: { name: "China",          flag: "🇨🇳", coords: [104.19, 35.86], index: "SSE Comp",    tz: "Asia/Shanghai",    marketOpen: 9.5,  marketClose: 15   },
  EU: { name: "Europe",         flag: "🇪🇺", coords: [10.0, 50.0],    index: "STOXX 600",   tz: "Europe/Berlin",    marketOpen: 9,    marketClose: 17.5 },
  JP: { name: "Japan",          flag: "🇯🇵", coords: [138.25, 36.20], index: "Nikkei 225",  tz: "Asia/Tokyo",       marketOpen: 9,    marketClose: 15   },
  GB: { name: "United Kingdom", flag: "🇬🇧", coords: [-2.0, 54.0],   index: "FTSE 100",    tz: "Europe/London",    marketOpen: 8,    marketClose: 16.5 },
  SA: { name: "Middle East",    flag: "🇸🇦", coords: [45.08, 23.88],  index: "Tadawul",     tz: "Asia/Riyadh",      marketOpen: 10,   marketClose: 15   },
  RU: { name: "Russia",         flag: "🇷🇺", coords: [105.32, 61.52], index: "MOEX",        tz: "Europe/Moscow",    marketOpen: 10,   marketClose: 18.5 },
};

function isMarketOpen(c) {
  try {
    const now = new Date();
    const formatter = new Intl.DateTimeFormat("en-US", { timeZone: c.tz, hour: "numeric", minute: "numeric", hour12: false, weekday: "short" });
    const parts = formatter.formatToParts(now);
    const weekday = parts.find(p => p.type === "weekday")?.value;
    const hour = parseInt(parts.find(p => p.type === "hour")?.value || "0");
    const minute = parseInt(parts.find(p => p.type === "minute")?.value || "0");
    const time = hour + minute / 60;
    if (weekday === "Sat" || weekday === "Sun") return false;
    return time >= c.marketOpen && time < c.marketClose;
  } catch { return false; }
}

// -----------------------------------------------------------------------
// CSS Keyframes (injected once)
// -----------------------------------------------------------------------
const GLOBE_STYLES = `
@keyframes pulseRing {
  0% { r: 4; opacity: 0.6; }
  100% { r: 14; opacity: 0; }
}
@keyframes pulseGlow {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.7; }
}
@keyframes scrollTicker {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes rotateGlobe {
  from { --globe-rot: 0; }
  to { --globe-rot: 360; }
}
`;

export default function GlobeNewsSection() {
  const [rotation, setRotation] = useState([-30, -20, 0]);
  const [scale, setScale] = useState(190);
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [news, setNews] = useState([]);
  const [loadingNews, setLoadingNews] = useState(false);
  const [impact, setImpact] = useState(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [autoRotate, setAutoRotate] = useState(true);
  const [marketStatus, setMarketStatus] = useState({});
  const [newsCount, setNewsCount] = useState({});

  // Refs
  const isDragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });
  const containerRef = useRef(null);
  const autoRotateRef = useRef(null);
  const styleRef = useRef(null);

  // Inject styles once
  useEffect(() => {
    if (!styleRef.current) {
      const style = document.createElement("style");
      style.textContent = GLOBE_STYLES;
      document.head.appendChild(style);
      styleRef.current = style;
    }
    return () => { if (styleRef.current) { styleRef.current.remove(); styleRef.current = null; } };
  }, []);

  // Market status refresh every 60s
  useEffect(() => {
    const update = () => {
      const status = {};
      Object.entries(COUNTRY_INFO).forEach(([code, c]) => { status[code] = isMarketOpen(c); });
      setMarketStatus(status);
    };
    update();
    const timer = setInterval(update, 60000);
    return () => clearInterval(timer);
  }, []);

  // Auto-rotation
  useEffect(() => {
    if (autoRotate && !selected) {
      autoRotateRef.current = setInterval(() => {
        setRotation(prev => [prev[0] - 0.15, prev[1], 0]);
      }, 30);
    } else {
      clearInterval(autoRotateRef.current);
    }
    return () => clearInterval(autoRotateRef.current);
  }, [autoRotate, selected]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e) => {
      if (!containerRef.current?.contains(document.activeElement) && document.activeElement !== document.body) return;
      const codes = Object.keys(COUNTRY_INFO);
      switch (e.key) {
        case "ArrowLeft": e.preventDefault(); setRotation(p => [p[0] + 15, p[1], 0]); setAutoRotate(false); break;
        case "ArrowRight": e.preventDefault(); setRotation(p => [p[0] - 15, p[1], 0]); setAutoRotate(false); break;
        case "ArrowUp": e.preventDefault(); setRotation(p => [p[0], Math.min(60, p[1] + 10), 0]); setAutoRotate(false); break;
        case "ArrowDown": e.preventDefault(); setRotation(p => [p[0], Math.max(-60, p[1] - 10), 0]); setAutoRotate(false); break;
        case "+": case "=": e.preventDefault(); setScale(s => Math.min(300, s + 20)); break;
        case "-": case "_": e.preventDefault(); setScale(s => Math.max(100, s - 20)); break;
        case "Escape": setSelected(null); setNews([]); setImpact(null); setAutoRotate(true); break;
        case "Tab":
          if (!selected) {
            e.preventDefault();
            handleSelect(codes[0]);
          } else {
            e.preventDefault();
            const idx = codes.indexOf(selected);
            handleSelect(codes[(idx + 1) % codes.length]);
          }
          break;
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [selected]);

  // Drag handlers
  const handlePointerDown = (e) => {
    isDragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setAutoRotate(false);
  };
  const handlePointerMove = (e) => {
    if (!isDragging.current) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setRotation(prev => [prev[0] - dx * 0.5, Math.max(-60, Math.min(60, prev[1] + dy * 0.5)), 0]);
  };
  const handlePointerUp = () => { isDragging.current = false; };

  // Zoom handlers
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    setScale(s => Math.max(100, Math.min(300, s - e.deltaY * 0.3)));
    setAutoRotate(false);
  }, []);

  // Fetch news
  const fetchNews = useCallback(async (code) => {
    setLoadingNews(true); setNews([]); setImpact(null);
    try {
      const res = await fetch(`${API_BASE}/api/global-news/${code}`);
      const data = await res.json();
      setNews(data.news || []);
      setNewsCount(prev => ({ ...prev, [code]: data.news?.length || 0 }));
      if (data.news?.length > 0) fetchImpact(code, data.news.map(n => n.headline));
    } catch (e) { console.error("News fetch error:", e); }
    finally { setLoadingNews(false); }
  }, []);

  const fetchImpact = async (code, headlines) => {
    setLoadingImpact(true);
    try {
      const res = await fetch(`${API_BASE}/api/global-news/portfolio-impact`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_code: code, headlines }),
      });
      setImpact(await res.json());
    } catch (e) { console.error("Impact error:", e); }
    finally { setLoadingImpact(false); }
  };

  const handleSelect = useCallback((code) => {
    setSelected(code); setAutoRotate(false);
    fetchNews(code);
    const info = COUNTRY_INFO[code];
    if (info) setRotation([-info.coords[0], -info.coords[1], 0]);
  }, [fetchNews]);

  const info = selected ? COUNTRY_INFO[selected] : null;
  const hoveredInfo = hovered ? COUNTRY_INFO[hovered] : null;

  return (
    <div style={{ marginBottom: "24px", overflow: "hidden", maxWidth: "1400px", margin: "0 auto" }} ref={containerRef} tabIndex={0} role="region" aria-label="Global Market Intelligence">
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px", padding: "0 10px" }}>
        <div style={{
          width: "36px", height: "36px", borderRadius: "10px",
          background: "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(6,182,212,0.15))",
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: "18px",
        }}>🌍</div>
        <div>
          <h2 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", letterSpacing: "0.02em" }}>
            Global Intelligence
          </h2>
          <p style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "1px" }}>
            Real-time market news from {Object.keys(COUNTRY_INFO).length} regions • Arrow keys to navigate
          </p>
        </div>
        <div style={{ flex: 1 }} />
        {/* Market Status Bar */}
        <div className="market-status-bar">
          {Object.entries(COUNTRY_INFO).slice(0, 5).map(([code, c]) => (
            <div key={code} title={`${c.name}: ${marketStatus[code] ? "Market Open" : "Market Closed"}`}
              style={{ display: "flex", alignItems: "center", gap: "3px", padding: "3px 8px", borderRadius: "6px", background: "rgba(17,24,39,0.6)", border: "1px solid var(--border-subtle)", fontSize: "10px", cursor: "pointer" }}
              onClick={() => handleSelect(code)}
            >
              <span>{c.flag}</span>
              <span style={{
                width: "6px", height: "6px", borderRadius: "50%",
                background: marketStatus[code] ? "var(--color-accent-green)" : "rgba(148,163,184,0.3)",
                boxShadow: marketStatus[code] ? "0 0 6px rgba(16,185,129,0.5)" : "none",
              }} />
            </div>
          ))}
        </div>
      </div>

      <div className={`globe-container ${selected ? '' : 'no-selection'}`} style={{
        background: "linear-gradient(135deg, rgba(6,8,18,0.95), rgba(10,14,28,0.9))",
        backdropFilter: "blur(20px)",
        border: "1px solid rgba(99,102,241,0.12)",
        borderRadius: "20px",
        overflow: "hidden",
        minHeight: selected ? "auto" : "460px",
        boxShadow: "0 4px 40px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03)",
      }}>
        {/* LEFT: Globe */}
        <div className={`globe-left ${selected ? '' : 'full-width'}`} style={{
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          padding: "14px", position: "relative",
          borderRight: selected ? "1px solid rgba(99,102,241,0.1)" : "none",
        }}>
          {/* Globe Controls */}
          <div style={{ position: "absolute", top: "16px", right: "16px", display: "flex", flexDirection: "column", gap: "4px", zIndex: 10 }}>
            <button onClick={() => setScale(s => Math.min(300, s + 20))} aria-label="Zoom in"
              style={{ width: "30px", height: "30px", borderRadius: "8px", border: "1px solid rgba(99,102,241,0.2)", background: "rgba(10,14,28,0.8)", color: "var(--color-text-muted)", fontSize: "16px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "var(--color-accent-primary)"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "rgba(99,102,241,0.2)"}
            >+</button>
            <button onClick={() => setScale(s => Math.max(100, s - 20))} aria-label="Zoom out"
              style={{ width: "30px", height: "30px", borderRadius: "8px", border: "1px solid rgba(99,102,241,0.2)", background: "rgba(10,14,28,0.8)", color: "var(--color-text-muted)", fontSize: "16px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "var(--color-accent-primary)"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "rgba(99,102,241,0.2)"}
            >−</button>
            <button onClick={() => { setAutoRotate(!autoRotate); }} aria-label={autoRotate ? "Pause rotation" : "Resume rotation"} title={autoRotate ? "Pause auto-rotate" : "Resume auto-rotate"}
              style={{ width: "30px", height: "30px", borderRadius: "8px", border: "1px solid rgba(99,102,241,0.2)", background: autoRotate ? "rgba(99,102,241,0.15)" : "rgba(10,14,28,0.8)", color: autoRotate ? "var(--color-accent-primary)" : "var(--color-text-muted)", fontSize: "12px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
            >{autoRotate ? "⏸" : "▶"}</button>
            <button onClick={() => { setRotation([-30, -20, 0]); setScale(190); setAutoRotate(true); }} aria-label="Reset view" title="Reset view"
              style={{ width: "30px", height: "30px", borderRadius: "8px", border: "1px solid rgba(99,102,241,0.2)", background: "rgba(10,14,28,0.8)", color: "var(--color-text-muted)", fontSize: "12px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
            >↺</button>
          </div>

          {/* Hover Tooltip */}
          {hovered && !selected && hoveredInfo && (
            <div style={{
              position: "absolute", top: "16px", left: "16px", padding: "10px 14px",
              background: "rgba(10,14,28,0.95)", border: "1px solid rgba(99,102,241,0.25)",
              borderRadius: "10px", zIndex: 10, animation: "fadeSlideUp 0.2s ease",
              backdropFilter: "blur(10px)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                <span style={{ fontSize: "20px" }}>{hoveredInfo.flag}</span>
                <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--color-text-primary)" }}>{hoveredInfo.name}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px" }}>
                <span style={{ color: "var(--color-text-muted)" }}>{hoveredInfo.index}</span>
                <span style={{
                  width: "5px", height: "5px", borderRadius: "50%",
                  background: marketStatus[hovered] ? "var(--color-accent-green)" : "rgba(148,163,184,0.4)",
                }} />
                <span style={{ color: marketStatus[hovered] ? "var(--color-accent-green)" : "var(--color-text-muted)", fontWeight: 600 }}>
                  {marketStatus[hovered] ? "Open" : "Closed"}
                </span>
              </div>
              {newsCount[hovered] > 0 && (
                <div style={{ fontSize: "10px", color: "var(--color-accent-cyan)", marginTop: "4px" }}>
                  📰 {newsCount[hovered]} headlines cached
                </div>
              )}
            </div>
          )}

          {/* SVG Globe */}
           <div
            style={{
              width: "100%", maxWidth: "320px",
              cursor: isDragging.current ? "grabbing" : "grab",
              userSelect: "none", touchAction: "none",
            }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
            onWheel={handleWheel}
          >
            <ComposableMap
              projection="geoOrthographic"
              projectionConfig={{ rotate: rotation, scale }}
              width={400} height={400}
              style={{ width: "100%", height: "auto" }}
            >
              <defs>
                {/* Atmospheric glow gradient */}
                <radialGradient id="globeGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="85%" stopColor="transparent" />
                  <stop offset="92%" stopColor="rgba(99,102,241,0.06)" />
                  <stop offset="97%" stopColor="rgba(99,102,241,0.12)" />
                  <stop offset="100%" stopColor="rgba(99,102,241,0.04)" />
                </radialGradient>
                <radialGradient id="oceanGrad" cx="40%" cy="35%" r="60%">
                  <stop offset="0%" stopColor="rgba(15,20,40,0.95)" />
                  <stop offset="100%" stopColor="rgba(6,8,18,0.98)" />
                </radialGradient>
                {/* Selected country glow */}
                <radialGradient id="selectedGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="rgba(99,102,241,0.4)" />
                  <stop offset="100%" stopColor="rgba(99,102,241,0)" />
                </radialGradient>
              </defs>

              {/* Outer atmosphere */}
              <circle cx={200} cy={200} r={scale + 8} fill="url(#globeGlow)" />
              {/* Ocean */}
              <circle cx={200} cy={200} r={scale} fill="url(#oceanGrad)" stroke="rgba(99,102,241,0.15)" strokeWidth={0.5} />
              {/* Grid lines effect */}
              <circle cx={200} cy={200} r={scale} fill="none" stroke="rgba(99,102,241,0.04)" strokeWidth={16} />

              <Geographies geography={GEO_URL}>
                {({ geographies }) =>
                  geographies.map((geo) => {
                    const code = COUNTRY_MAP[geo.id];
                    const isHighlighted = !!code;
                    const isSelected = code === selected;
                    const isHovered = code === hovered;

                    return (
                      <Geography
                        key={geo.rsmKey}
                        geography={geo}
                        onClick={() => { if (code) handleSelect(code); }}
                        onMouseEnter={() => { if (code) setHovered(code); }}
                        onMouseLeave={() => setHovered(null)}
                        style={{
                          default: {
                            fill: isSelected ? "rgba(99,102,241,0.55)"
                              : isHovered ? "rgba(99,102,241,0.35)"
                              : isHighlighted ? "rgba(99,102,241,0.18)"
                              : "rgba(30,41,59,0.7)",
                            stroke: isSelected ? "rgba(129,140,248,0.5)"
                              : isHighlighted ? "rgba(99,102,241,0.2)"
                              : "rgba(71,85,105,0.2)",
                            strokeWidth: isSelected ? 1.2 : 0.3,
                            outline: "none",
                            cursor: isHighlighted ? "pointer" : "default",
                            transition: "fill 0.3s ease, stroke 0.3s ease",
                          },
                          hover: {
                            fill: isHighlighted ? "rgba(99,102,241,0.42)" : "rgba(51,65,85,0.8)",
                            stroke: isHighlighted ? "rgba(129,140,248,0.5)" : "rgba(71,85,105,0.3)",
                            strokeWidth: isHighlighted ? 1 : 0.3,
                            outline: "none",
                            cursor: isHighlighted ? "pointer" : "default",
                          },
                          pressed: { fill: "rgba(99,102,241,0.5)", outline: "none" },
                        }}
                      />
                    );
                  })
                }
              </Geographies>

              {/* Connection arc from selected to India */}
              {selected && selected !== "IN" && (
                <Line
                  from={COUNTRY_INFO[selected].coords}
                  to={COUNTRY_INFO.IN.coords}
                  stroke="rgba(6,182,212,0.25)"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  strokeLinecap="round"
                />
              )}

              {/* Country markers */}
              {Object.entries(COUNTRY_INFO).map(([code, c]) => {
                const isSel = code === selected;
                const isHov = code === hovered;
                const open = marketStatus[code];
                return (
                  <Marker key={code} coordinates={c.coords}>
                    {/* Pulsing ring for selected */}
                    {isSel && (
                      <>
                        <circle r={4} fill="none" stroke="#818cf8" strokeWidth={1.5}
                          style={{ animation: "pulseRing 2s ease-out infinite" }} />
                        <circle r={4} fill="none" stroke="#818cf8" strokeWidth={1}
                          style={{ animation: "pulseRing 2s ease-out infinite 0.7s" }} />
                      </>
                    )}
                    {/* Main dot */}
                    <circle
                      r={isSel ? 5.5 : isHov ? 4.5 : 3.5}
                      fill={isSel ? "#818cf8" : isHov ? "rgba(129,140,248,0.8)" : open ? "rgba(16,185,129,0.6)" : "rgba(129,140,248,0.5)"}
                      stroke={isSel ? "#fff" : isHov ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.25)"}
                      strokeWidth={isSel ? 2 : 0.8}
                      style={{ cursor: "pointer", transition: "all 0.3s ease", filter: isSel ? "drop-shadow(0 0 6px rgba(129,140,248,0.6))" : "none" }}
                      onClick={(e) => { e.stopPropagation(); handleSelect(code); }}
                      onMouseEnter={() => setHovered(code)}
                      onMouseLeave={() => setHovered(null)}
                    />
                    {/* Label with market status */}
                    <text
                      textAnchor="middle" y={isSel ? -14 : -10}
                      style={{
                        fontFamily: "system-ui, sans-serif",
                        fontSize: isSel ? "9px" : "7px",
                        fontWeight: 700,
                        fill: isSel ? "#e0e7ff" : isHov ? "#94a3b8" : "rgba(148,163,184,0.5)",
                        pointerEvents: "none", transition: "all 0.3s",
                      }}
                    >
                      {c.flag} {code}
                    </text>
                  </Marker>
                );
              })}
            </ComposableMap>
          </div>

          {/* Quick select pills */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", justifyContent: "center", marginTop: "6px", maxWidth: "340px" }}>
            {Object.entries(COUNTRY_INFO).map(([code, c]) => {
              const isActive = selected === code;
              const open = marketStatus[code];
              return (
                <button key={code} onClick={() => handleSelect(code)}
                  aria-label={`View ${c.name} market intelligence`}
                  aria-pressed={isActive}
                  style={{
                    display: "flex", alignItems: "center", gap: "5px",
                    padding: "6px 12px", borderRadius: "999px",
                    border: isActive ? "1.5px solid var(--color-accent-primary)" : "1px solid rgba(99,102,241,0.12)",
                    background: isActive ? "rgba(99,102,241,0.2)" : "rgba(10,14,28,0.6)",
                    color: isActive ? "#fff" : "var(--color-text-secondary)",
                    fontSize: "10px", fontWeight: 600, cursor: "pointer",
                    transition: "all 0.25s",
                    boxShadow: isActive ? "0 0 12px rgba(99,102,241,0.2)" : "none",
                  }}
                  onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.borderColor = "rgba(99,102,241,0.4)"; e.currentTarget.style.background = "rgba(99,102,241,0.08)"; }}}
                  onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.borderColor = "rgba(99,102,241,0.12)"; e.currentTarget.style.background = "rgba(10,14,28,0.6)"; }}}
                >
                  <span style={{ fontSize: "13px" }}>{c.flag}</span>
                  <span>{c.name}</span>
                  <span style={{
                    width: "5px", height: "5px", borderRadius: "50%", flexShrink: 0,
                    background: open ? "var(--color-accent-green)" : "rgba(148,163,184,0.25)",
                    boxShadow: open ? "0 0 4px rgba(16,185,129,0.4)" : "none",
                  }} />
                </button>
              );
            })}
          </div>

          {/* Hint */}
          <p style={{ marginTop: "4px", fontSize: "10px", color: "var(--color-text-muted)", textAlign: "center" }}>
            {info ? `${info.flag} ${info.name} • ${info.index}` : "Drag to rotate • Scroll to zoom • ← → ↑ ↓ keys"}
          </p>
        </div>

        {/* RIGHT: News + Impact Panel */}
        {selected && info && (
          <div className="globe-right" style={{ padding: "16px 18px", overflowY: "auto", overflowX: "hidden", maxHeight: "520px", animation: "fadeSlideUp 0.35s ease-out" }}>
            {/* Panel Header */}
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "18px" }}>
              <div style={{
                width: "44px", height: "44px", borderRadius: "12px",
                background: "linear-gradient(135deg, rgba(99,102,241,0.15), rgba(6,182,212,0.1))",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: "24px",
                border: "1px solid rgba(99,102,241,0.15)",
              }}>{info.flag}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <h3 style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>{info.name}</h3>
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: "4px",
                    padding: "2px 8px", borderRadius: "999px", fontSize: "9px", fontWeight: 700,
                    background: marketStatus[selected] ? "rgba(16,185,129,0.12)" : "rgba(148,163,184,0.08)",
                    color: marketStatus[selected] ? "var(--color-accent-green)" : "var(--color-text-muted)",
                    border: `1px solid ${marketStatus[selected] ? "rgba(16,185,129,0.2)" : "rgba(148,163,184,0.1)"}`,
                    textTransform: "uppercase", letterSpacing: "0.05em",
                  }}>
                    <span style={{
                      width: "5px", height: "5px", borderRadius: "50%",
                      background: marketStatus[selected] ? "var(--color-accent-green)" : "rgba(148,163,184,0.4)",
                    }} />
                    {marketStatus[selected] ? "Open" : "Closed"}
                  </span>
                </div>
                <p style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px" }}>
                  {info.index} • {news.length} headlines • Financial news & portfolio impact
                </p>
              </div>
              <button onClick={() => { setSelected(null); setNews([]); setImpact(null); setAutoRotate(true); }}
                aria-label="Close panel"
                style={{ padding: "6px 12px", borderRadius: "8px", border: "1px solid var(--border-subtle)", background: "transparent", color: "var(--color-text-muted)", fontSize: "11px", cursor: "pointer", transition: "all 0.15s" }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "var(--color-accent-red)"; e.currentTarget.style.borderColor = "var(--color-accent-red)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.borderColor = "var(--border-subtle)"; }}
              >✕ Close</button>
            </div>

            {/* News List */}
            {loadingNews ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "12px" }}>
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i} className="shimmer" style={{ height: "80px", borderRadius: "10px" }} />
                ))}
              </div>
            ) : news.length === 0 ? (
              <div style={{ padding: "40px 20px", textAlign: "center" }}>
                <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }}>📭</span>
                <p style={{ fontSize: "13px", color: "var(--color-text-muted)" }}>No news available for {info.name} right now.</p>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "12px", marginBottom: "18px" }}>
                {news.map((item, i) => (
                  <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                    style={{
                      display: "flex", flexDirection: "column", justifyContent: "space-between",
                      padding: "14px 16px",
                      background: "rgba(15,20,35,0.6)",
                      border: "1px solid rgba(99,102,241,0.08)",
                      borderRadius: "10px", textDecoration: "none",
                      transition: "all 0.2s",
                      animation: `fadeSlideUp 0.3s ease-out ${i * 0.04}s both`,
                      height: "100%",
                      minHeight: "90px",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "rgba(99,102,241,0.3)";
                      e.currentTarget.style.background = "rgba(15,20,35,0.9)";
                      e.currentTarget.style.transform = "translateY(-3px)";
                      e.currentTarget.style.boxShadow = "0 8px 24px rgba(0,0,0,0.2)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "rgba(99,102,241,0.08)";
                      e.currentTarget.style.background = "rgba(15,20,35,0.6)";
                      e.currentTarget.style.transform = "translateY(0)";
                      e.currentTarget.style.boxShadow = "none";
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", marginBottom: "12px" }}>
                      <span style={{
                        fontSize: "8px", fontWeight: 700, color: "rgba(99,102,241,0.6)",
                        width: "18px", height: "18px", display: "flex", alignItems: "center", justifyContent: "center",
                        borderRadius: "5px", flexShrink: 0, marginTop: "2px",
                        background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.1)",
                      }}>{i + 1}</span>
                      <p style={{ flex: 1, fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", lineHeight: 1.45, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical" }}>
                        {item.headline}
                      </p>
                    </div>
                    
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "auto" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{
                          fontSize: "9px", fontWeight: 700, color: "var(--color-accent-cyan)",
                          padding: "2px 7px", borderRadius: "4px", background: "rgba(6,182,212,0.08)", border: "1px solid rgba(6,182,212,0.1)",
                        }}>{item.source}</span>
                        <span style={{ fontSize: "10px", color: "var(--color-text-muted)" }}>{item.published_date}</span>
                      </div>
                      <span style={{ fontSize: "12px", color: "rgba(99,102,241,0.5)", fontWeight: 700 }}>↗</span>
                    </div>
                  </a>
                ))}
              </div>
            )}

            {/* AI Impact */}
            <div style={{
              padding: "18px",
              background: "linear-gradient(135deg, rgba(10,14,23,0.8), rgba(17,24,39,0.5))",
              border: "1px solid rgba(99,102,241,0.1)", borderRadius: "14px",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
                <div style={{
                  width: "28px", height: "28px", borderRadius: "8px",
                  background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: "14px",
                }}>🧠</div>
                <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)" }}>AI Portfolio Impact</h4>
                {selected !== "IN" && (
                  <span style={{ marginLeft: "auto", fontSize: "10px", color: "var(--color-accent-cyan)", opacity: 0.6 }}>
                    {info.flag} → 🇮🇳 Impact
                  </span>
                )}
              </div>

              {loadingImpact ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <div className="shimmer" style={{ height: "48px", borderRadius: "8px" }} />
                  <div className="shimmer" style={{ height: "32px", borderRadius: "8px", width: "70%" }} />
                </div>
              ) : impact ? (
                <>
                  <p style={{
                    fontSize: "13px", lineHeight: 1.65, color: "var(--color-text-secondary)",
                    marginBottom: impact.affected_stocks?.length > 0 ? "16px" : "0",
                    borderLeft: "3px solid var(--color-accent-primary)", paddingLeft: "12px",
                  }}>{impact.impact_summary}</p>
                  {impact.affected_stocks?.length > 0 && (
                    <>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "12px" }}>
                        {impact.affected_stocks.map((s, i) => {
                          const clr = s.impact === "positive" ? "var(--color-accent-green)" : s.impact === "negative" ? "var(--color-accent-red)" : "var(--color-accent-amber)";
                          const bg = s.impact === "positive" ? "rgba(16,185,129,0.1)" : s.impact === "negative" ? "rgba(239,68,68,0.1)" : "rgba(245,158,11,0.1)";
                          const icon = s.impact === "positive" ? "▲" : s.impact === "negative" ? "▼" : "●";
                          return (
                            <div key={i} title={s.reason} style={{
                              display: "flex", alignItems: "center", gap: "5px",
                              padding: "6px 10px", borderRadius: "8px",
                              background: bg, border: `1px solid ${clr}22`,
                              animation: `fadeSlideUp 0.3s ease-out ${i * 0.06}s both`,
                            }}>
                              <span style={{ fontSize: "9px", color: clr }}>{icon}</span>
                              <span style={{ fontSize: "11px", fontWeight: 700, color: "var(--color-text-primary)" }}>{s.ticker}</span>
                              <span style={{ fontSize: "9px", color: clr, fontWeight: 600, textTransform: "uppercase" }}>{s.impact}</span>
                            </div>
                          );
                        })}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                        {impact.affected_stocks.map((s, i) => (
                          <p key={i} style={{ fontSize: "11px", color: "var(--color-text-muted)", lineHeight: 1.5 }}>
                            <span style={{ fontWeight: 700, color: "var(--color-text-secondary)" }}>{s.ticker}:</span>{" "}
                            {s.reason}
                          </p>
                        ))}
                      </div>
                    </>
                  )}
                </>
              ) : (
                <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>Analyzing portfolio impact...</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bottom: Scrolling News Ticker */}
      {news.length > 0 && selected && (
        <div style={{
          marginTop: "10px", overflow: "hidden", borderRadius: "10px",
          background: "rgba(6,8,18,0.6)", border: "1px solid rgba(99,102,241,0.08)",
          padding: "8px 0", maxWidth: "100%",
        }}>
          <div style={{
            display: "flex", gap: "40px", whiteSpace: "nowrap", width: "max-content",
            animation: `scrollTicker ${news.length * 5}s linear infinite`,
          }}>
            {[...news, ...news].map((item, i) => (
              <span key={i} style={{ fontSize: "11px", color: "var(--color-text-muted)", flexShrink: 0 }}>
                <span style={{ color: "var(--color-accent-cyan)", fontWeight: 700, marginRight: "6px" }}>{info?.flag}</span>
                {item.headline}
                <span style={{ margin: "0 20px", color: "rgba(99,102,241,0.3)" }}>|</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
