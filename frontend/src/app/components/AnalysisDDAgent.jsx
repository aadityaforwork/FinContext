import { useState, useRef, useEffect } from "react";
import AnalysisVideoPresenter from "./AnalysisVideoPresenter";

import { API_BASE as _SHARED_API_BASE } from "../lib/api";
const API_BASE = _SHARED_API_BASE;

export default function AnalysisDDAgent({ ticker, stockName }) {
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [showVideo, setShowVideo] = useState(false);
  const terminalRef = useRef(null);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [steps]);

  const deployAgent = async () => {
    setRunning(true);
    setSteps([]);
    setResult(null);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/analysis/dd-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });

      if (!response.ok) throw new Error("Agent failed to initialize");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let done = false;
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        if (value) {
          const chunk = decoder.decode(value);
          const lines = chunk.split("\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.slice(6).trim();
              if (dataStr === "[DONE]") {
                setRunning(false);
                break;
              }
              if (dataStr) {
                try {
                  const data = JSON.parse(dataStr);
                  if (data.type === "step") {
                    setSteps((prev) => [...prev, data.message]);
                  } else if (data.type === "result") {
                    setResult(data);
                    setRunning(false); // Finished generating result
                  }
                } catch (e) {
                  // handle partial chunks if needed, simple approach for MVP
                  console.error("Parse error stream:", e);
                }
              }
            }
          }
        }
        done = readerDone;
      }
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  return (
    <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "20px" }}>📖</span> AI Stock Story (ELI5)
          </h3>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
            Deploy a Friendly Financial Educator to translate {stockName}'s complex financials into a simple analogy and health score.
          </p>
        </div>
        {!result && (
          <button
            onClick={deployAgent}
            disabled={running}
            style={{
              padding: "10px 20px", borderRadius: "10px", fontSize: "13px", fontWeight: 600,
              background: running ? "var(--color-bg-tertiary)" : "var(--color-text-primary)",
              color: running ? "var(--color-text-muted)" : "var(--color-bg-primary)", border: "none", cursor: running ? "not-allowed" : "pointer",
              transition: "all 0.2s ease"
            }}
          >
            {running ? "Agent Active..." : "Deploy Agent"}
          </button>
        )}
      </div>

      {error && <div style={{ color: "var(--color-accent-red)", fontSize: "13px", padding: "12px", background: "rgba(239,68,68,0.1)", borderRadius: "8px", marginBottom: "20px" }}>{error}</div>}

      {/* Terminal UI */}
      {(running || (steps.length > 0 && !result)) && (
        <div style={{ 
          background: "#0c0a13", border: "1px solid #2a2542", borderRadius: "12px", 
          padding: "16px", fontFamily: "'JetBrains Mono', monospace", fontSize: "13px", color: "#a599e9",
          minHeight: "150px", overflowY: "auto", marginBottom: "20px"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid #2a2542" }}>
            <div style={{ display: "flex", gap: "6px" }}>
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#ef4444" }}></div>
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#f59e0b" }}></div>
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#10b981" }}></div>
            </div>
            <span style={{ fontSize: "11px", color: "#6b61a3", textTransform: "uppercase", letterSpacing: "1px" }}>Analyst Execution Terminal</span>
          </div>
          
          <div ref={terminalRef} style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "200px", overflowY: "auto" }}>
            {steps.map((step, idx) => (
              <div key={idx} className="animate-fade-up">
                <span style={{ color: "#34d399", marginRight: "10px" }}>&gt;</span>
                {step}
              </div>
            ))}
            {running && (
              <div style={{ color: "var(--color-text-muted)", animation: "pulse 1.5s infinite" }}>
                <span style={{ color: "#34d399", marginRight: "10px" }}>&gt;</span> _
              </div>
            )}
          </div>
        </div>
      )}

      {/* ELI5 Stock Story Result */}
      {result && (
        <div className="animate-fade-up" style={{ 
          background: "linear-gradient(to bottom right, rgba(255,255,255,0.03), rgba(255,255,255,0.01))", 
          border: "1px solid var(--border-subtle)", borderRadius: "16px", padding: "28px" 
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "20px", marginBottom: "20px" }}>
            <div>
              <span style={{ padding: "4px 8px", borderRadius: "4px", fontSize: "10px", fontWeight: 700, background: "var(--color-bg-tertiary)", color: "var(--color-text-secondary)", letterSpacing: "1px", textTransform: "uppercase" }}>ELI5 Explainer</span>
              <h4 style={{ fontSize: "22px", fontWeight: 700, color: "var(--color-text-primary)", marginTop: "12px" }}>{result.company} ({ticker})</h4>
            </div>
            <div className="dd-header-actions">
              <button
                 onClick={() => setShowVideo(true)}
                 style={{ background: "var(--color-text-primary)", color: "var(--color-bg-primary)", border: "none", padding: "6px 16px", borderRadius: "8px", fontSize: "12px", fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: "6px", transition: "all 0.2s" }}
              >
                ▶ Play Video Brief
              </button>
              <button
                 onClick={() => { setResult(null); setSteps([]); }}
                 style={{ background: "transparent", border: "1px solid var(--border-subtle)", color: "var(--color-text-muted)", padding: "6px 14px", borderRadius: "8px", fontSize: "12px", cursor: "pointer", transition: "all 0.2s" }}
                 onMouseEnter={(e) => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.borderColor = "var(--color-text-primary)"; }}
                 onMouseLeave={(e) => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.borderColor = "var(--border-subtle)"; }}
              >
                Start Over
              </button>
            </div>
          </div>

          <div className="responsive-grid-dd-hero" style={{ marginBottom: "24px" }}>
            {/* Health Score */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.2)", borderRadius: "16px", padding: "24px", border: "1px solid var(--border-subtle)" }}>
              <span style={{ fontSize: "12px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 600, marginBottom: "8px" }}>Health Score</span>
              <div style={{ position: "relative", width: "100px", height: "50px", overflow: "hidden", marginBottom: "8px" }}>
                <div style={{ 
                  position: "absolute", top: 0, left: 0, width: "100px", height: "100px", borderRadius: "50%",
                  border: "10px solid #2a2542", borderBottomColor: "transparent", borderRightColor: "transparent",
                  transform: "rotate(-45deg)"
                }}></div>
                <div style={{ 
                  position: "absolute", top: 0, left: 0, width: "100px", height: "100px", borderRadius: "50%",
                  border: "10px solid", borderBottomColor: "transparent", borderRightColor: "transparent",
                  borderColor: result.health_score > 70 ? "var(--color-accent-green)" : result.health_score > 40 ? "#f59e0b" : "var(--color-accent-red)",
                  transform: `rotate(${ -45 + (result.health_score / 100) * 180 }deg)`, transition: "transform 1s ease-out"
                }}></div>
              </div>
              <div style={{ fontSize: "36px", fontWeight: 800, color: "var(--color-text-primary)", lineHeight: 1 }}>{result.health_score}</div>
              <div style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "4px" }}>Out of 100</div>
            </div>

            {/* Analogy Bubble */}
            <div style={{ background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.15)", borderRadius: "16px", padding: "24px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
                <span style={{ fontSize: "20px" }}>💡</span>
                <span style={{ fontSize: "14px", fontWeight: 700, color: "#a5b4fc" }}>The Simple Explanation</span>
              </div>
              <p style={{ fontSize: "16px", color: "var(--color-text-primary)", lineHeight: 1.6, fontStyle: "italic" }}>"{result.analogy}"</p>
            </div>
          </div>

          <div className="responsive-grid-2">
            {/* Pros */}
            <div style={{ background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.1)", borderRadius: "12px", padding: "20px" }}>
              <h5 style={{ fontSize: "14px", color: "var(--color-accent-green)", fontWeight: 700, marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
                <span>What's going well</span>
              </h5>
              <ul style={{ padding: 0, margin: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "12px" }}>
                {result.pros?.map((point, idx) => (
                  <li key={idx} style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.5, display: "flex", gap: "10px" }}>
                    <span style={{ color: "var(--color-accent-green)", fontSize: "18px" }}>✓</span> {point}
                  </li>
                ))}
              </ul>
            </div>

            {/* Cons */}
            <div style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.1)", borderRadius: "12px", padding: "20px" }}>
              <h5 style={{ fontSize: "14px", color: "var(--color-accent-red)", fontWeight: 700, marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
                <span>What to worry about</span>
              </h5>
              <ul style={{ padding: 0, margin: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "12px" }}>
                {result.cons?.map((point, idx) => (
                  <li key={idx} style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.5, display: "flex", gap: "10px" }}>
                    <span style={{ color: "var(--color-accent-red)", fontSize: "18px" }}>✕</span> {point}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div style={{ marginTop: "24px", padding: "16px", background: "rgba(255,255,255,0.03)", borderRadius: "10px", display: "flex", alignItems: "center", gap: "16px" }}>
            <span style={{ fontSize: "24px" }}>🎯</span>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 600 }}>The Bottom Line</span>
              <p style={{ fontSize: "15px", color: "var(--color-text-primary)", marginTop: "4px", fontWeight: 600 }}>{result.bottom_line}</p>
            </div>
          </div>

        </div>
      )}

      {showVideo && (
        <AnalysisVideoPresenter 
          memo={result} 
          ticker={ticker} 
          onClose={() => setShowVideo(false)} 
        />
      )}
    </div>
  );
}
