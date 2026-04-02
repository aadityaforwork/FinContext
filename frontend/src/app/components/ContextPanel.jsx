"use client";

import { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function ContextPanel({ ticker, stockName }) {
  const [analysis, setAnalysis] = useState(null);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [displayedText, setDisplayedText] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (!ticker) return;

    setLoading(true);
    setDisplayedText("");
    setAnalysis(null);
    setSources([]);

    fetch(`${API_BASE}/api/stocks/${ticker}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ top_k: 5 }),
    })
      .then((res) => res.json())
      .then((data) => {
        setAnalysis(data.analysis);
        setSources(data.context_sources || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [ticker]);

  // Typing animation effect
  useEffect(() => {
    if (!analysis) return;
    setIsTyping(true);
    setDisplayedText("");

    let i = 0;
    const speed = 8;
    const timer = setInterval(() => {
      if (i < analysis.length) {
        setDisplayedText(analysis.slice(0, i + 1));
        i++;
      } else {
        clearInterval(timer);
        setIsTyping(false);
      }
    }, speed);

    return () => clearInterval(timer);
  }, [analysis]);

  if (!ticker) {
    return (
      <div
        className="glass-card"
        style={{
          padding: "32px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "300px",
        }}
      >
        <div
          style={{
            width: "64px",
            height: "64px",
            borderRadius: "16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "16px",
            background: "rgba(99,102,241,0.1)",
          }}
        >
          <span style={{ fontSize: "30px" }}>🧠</span>
        </div>
        <p style={{ fontSize: "14px", fontWeight: 500, color: "var(--color-text-secondary)" }}>
          AI Context Engine
        </p>
        <p style={{ fontSize: "12px", marginTop: "4px", textAlign: "center", maxWidth: "200px", color: "var(--color-text-muted)" }}>
          Select a stock to view AI-synthesized market context
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
      {/* Panel Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
            }}
          >
            <span style={{ fontSize: "14px" }}>🧠</span>
          </div>
          <div>
            <h3 style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>
              Market Context
            </h3>
            <p style={{ fontSize: "10px", color: "var(--color-text-muted)" }}>
              RAG-powered analysis • {ticker}
            </p>
          </div>
        </div>
        <span
          style={{
            padding: "4px 8px",
            borderRadius: "6px",
            fontSize: "10px",
            fontWeight: 500,
            background: "rgba(99,102,241,0.1)",
            color: "var(--color-accent-secondary)",
          }}
        >
          v0.1-live
        </span>
      </div>

      {/* Analysis Text */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {[100, 90, 80, 60].map((w, i) => (
            <div key={i} className="shimmer" style={{ height: "16px", borderRadius: "4px", width: `${w}%` }} />
          ))}
        </div>
      ) : (
        <div style={{ fontSize: "14px", lineHeight: "1.7", marginBottom: "20px", color: "var(--color-text-secondary)" }}>
          <p className={isTyping ? "typing-cursor" : ""}>
            {displayedText}
          </p>
        </div>
      )}

      {/* Source Attribution */}
      {sources.length > 0 && !loading && (
        <div style={{ marginTop: "20px", paddingTop: "16px", borderTop: "1px solid var(--border-subtle)" }}>
          <p
            style={{
              fontSize: "10px",
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "12px",
              color: "var(--color-text-muted)",
            }}
          >
            Context Sources
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {sources.slice(0, 4).map((src, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "8px",
                  padding: "10px",
                  borderRadius: "8px",
                  background: "rgba(255,255,255,0.02)",
                }}
              >
                <div
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    marginTop: "6px",
                    flexShrink: 0,
                    background: `hsl(${230 + idx * 30}, 70%, 60%)`,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p
                    style={{
                      fontSize: "12px",
                      fontWeight: 500,
                      color: "var(--color-text-primary)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {src.headline}
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "4px" }}>
                    <span style={{ fontSize: "10px", color: "var(--color-accent-secondary)" }}>
                      {src.source}
                    </span>
                    <span style={{ fontSize: "10px", color: "var(--color-text-muted)" }}>
                      {src.published_date}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        padding: "1px 6px",
                        borderRadius: "4px",
                        background: "rgba(16,185,129,0.1)",
                        color: "var(--color-accent-green)",
                      }}
                    >
                      {(src.relevance_score * 100).toFixed(0)}% match
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
