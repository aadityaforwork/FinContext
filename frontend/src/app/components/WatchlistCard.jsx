"use client";

export default function WatchlistCard({ stock, isSelected, onClick }) {
  const isPositive = stock.change_percent >= 0;

  return (
    <button
      onClick={onClick}
      className="animate-fade-in"
      style={{
        width: "100%",
        textAlign: "left",
        padding: "16px",
        borderRadius: "16px",
        transition: "all 0.3s",
        cursor: "pointer",
        background: isSelected ? "var(--color-bg-card-hover)" : "var(--color-bg-card)",
        border: isSelected ? "1px solid var(--border-active)" : "1px solid var(--border-subtle)",
        boxShadow: isSelected ? "var(--shadow-glow)" : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        {/* Left: Ticker + Name */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <span style={{ fontSize: "13px", fontWeight: 700, letterSpacing: "0.025em", color: "var(--color-text-primary)" }}>
              {stock.ticker}
            </span>
            <span
              style={{
                padding: "2px 6px",
                borderRadius: "4px",
                fontSize: "10px",
                fontWeight: 500,
                background: "rgba(99, 102, 241, 0.15)",
                color: "var(--color-accent-secondary)",
              }}
            >
              {stock.sector.split(" - ")[0]}
            </span>
          </div>
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {stock.name}
          </p>
        </div>

        {/* Right: Price + Change */}
        <div style={{ textAlign: "right", marginLeft: "12px" }}>
          <p style={{ fontSize: "13px", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>
            ₹{stock.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </p>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "4px", marginTop: "2px" }}>
            <svg style={{ width: "10px", height: "10px" }} viewBox="0 0 12 12" fill="none">
              <path
                d={isPositive ? "M6 2L10 7H2L6 2Z" : "M6 10L2 5H10L6 10Z"}
                fill={isPositive ? "var(--color-accent-green)" : "var(--color-accent-red)"}
              />
            </svg>
            <span
              style={{
                fontSize: "12px",
                fontWeight: 600,
                fontVariantNumeric: "tabular-nums",
                color: isPositive ? "var(--color-accent-green)" : "var(--color-accent-red)",
              }}
            >
              {isPositive ? "+" : ""}{stock.change_percent.toFixed(2)}%
            </span>
          </div>
        </div>
      </div>

      {/* Selected accent bar */}
      {isSelected && (
        <div
          style={{
            marginTop: "12px",
            height: "2px",
            borderRadius: "9999px",
            background: "linear-gradient(90deg, var(--color-accent-primary), var(--color-accent-cyan))",
          }}
        />
      )}
    </button>
  );
}
