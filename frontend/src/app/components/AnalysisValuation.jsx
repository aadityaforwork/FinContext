import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function AnalysisValuation({ ticker }) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleImpact = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/analysis/narrative-impact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (!res.ok) throw new Error("Valuation calculation failed");
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card animate-fade-in" style={{ padding: "24px", gridColumn: "1 / -1" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "20px" }}>🖩</span> Narrative-to-Numbers Valuation Engine
          </h3>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
            Paste breaking news, a management quote, or a tweet. The AI translates the unstructured text into quantitative financial models.
          </p>
        </div>
      </div>

      <div className="simulator-row" style={{ marginBottom: "20px" }}>
        <textarea
          placeholder='e.g., "Factory fire reported at Pune plant. Expected 2 month shutdown." or "Secures massive $2B order from European rail network..."'
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={loading}
          style={{
            flex: 1, padding: "16px", borderRadius: "12px", fontSize: "14px", fontFamily: "inherit",
            border: "1px solid var(--border-subtle)", outline: "none", resize: "none", minHeight: "100px",
            background: "rgba(0,0,0,0.2)", color: "var(--color-text-primary)", lineHeight: 1.5
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
          <button
            onClick={handleImpact}
            disabled={loading || !text.trim()}
            style={{
              padding: "16px 24px", borderRadius: "12px", fontSize: "14px", fontWeight: 600,
              background: loading ? "var(--color-bg-tertiary)" : "var(--color-text-primary)",
              color: loading ? "var(--color-text-muted)" : "var(--color-bg-primary)", border: "none", cursor: loading || !text.trim() ? "not-allowed" : "pointer",
              transition: "all 0.2s ease"
            }}
          >
            {loading ? "Quantifying..." : "Quantify Impact"}
          </button>
        </div>
      </div>

      {error && <div style={{ color: "var(--color-accent-red)", fontSize: "13px", padding: "12px", background: "rgba(239,68,68,0.1)", borderRadius: "8px" }}>{error}</div>}

      {result && (
        <div className="animate-fade-up valuation-result" style={{ 
          background: "linear-gradient(to right, rgba(99,102,241,0.05), rgba(99,102,241,0.01))", 
          border: "1px solid rgba(99,102,241,0.2)", borderRadius: "16px", padding: "24px",
        }}>
          {/* Sentiment & Action Dial */}
          <div className="valuation-left" style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 600 }}>Algorithmic Action</span>
            <div style={{ 
              fontSize: "28px", fontWeight: 800, margin: "12px 0",
              color: result.extraction.sentiment === "Positive" ? "var(--color-accent-green)" : result.extraction.sentiment === "Negative" ? "var(--color-accent-red)" : "var(--color-text-primary)"
            }}>
              {result.extraction.algorithmic_action}
            </div>
            <div style={{ display: "flex", gap: "10px", alignItems: "center", background: "rgba(0,0,0,0.2)", padding: "4px 12px", borderRadius: "20px" }}>
              <span style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>Severity:</span>
              <div style={{ display: "flex", gap: "2px" }}>
                {[...Array(10)].map((_, i) => (
                  <div key={i} style={{ 
                    width: "6px", height: "12px", borderRadius: "2px",
                    background: i < result.extraction.severity_1_to_10 
                      ? (result.extraction.sentiment === "Negative" ? "var(--color-accent-red)" : result.extraction.sentiment === "Positive" ? "var(--color-accent-green)" : "var(--color-text-secondary)")
                      : "#2a2542"
                  }}></div>
                ))}
              </div>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "white" }}>{result.extraction.severity_1_to_10}/10</span>
            </div>
          </div>

          {/* Extracted Metrics */}
          <div className="valuation-right" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 600, marginBottom: "16px" }}>Quantitative Output</span>
            
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: "1px dashed var(--border-subtle)", paddingBottom: "8px" }}>
                <span style={{ fontSize: "14px", color: "var(--color-text-secondary)" }}>Est. Price Impact (Immediate)</span>
                <span style={{ fontSize: "16px", fontWeight: 700, fontFamily: "monospace", color: result.extraction.estimated_price_impact_percent > 0 ? "var(--color-accent-green)" : result.extraction.estimated_price_impact_percent < 0 ? "var(--color-accent-red)" : "var(--color-text-primary)" }}>
                  {result.extraction.estimated_price_impact_percent > 0 ? "+" : ""}{result.extraction.estimated_price_impact_percent}%
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: "1px dashed var(--border-subtle)", paddingBottom: "8px" }}>
                <span style={{ fontSize: "14px", color: "var(--color-text-secondary)" }}>EBITDA Shock</span>
                <span style={{ fontSize: "16px", fontWeight: 700, fontFamily: "monospace", color: "var(--color-text-primary)" }}>
                  {result.model_adjustments.ebitda}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: "14px", color: "var(--color-text-secondary)" }}>Revenue Adjustment</span>
                <span style={{ fontSize: "16px", fontWeight: 700, fontFamily: "monospace", color: "var(--color-text-primary)" }}>
                  {result.model_adjustments.revenue}
                </span>
              </div>
            </div>
            
            <p style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "16px", fontStyle: "italic" }}>
               Note: {result.risk_factors[0]}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
