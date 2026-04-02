"use client";

export default function Sidebar({ activeNav, onNavChange }) {
  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: "📊" },
    { id: "portfolio", label: "Portfolio", icon: "💼" },
    { id: "analysis", label: "Analysis", icon: "🧠" },
    { id: "company", label: "Company", icon: "🏢" },
    { id: "watchlist", label: "Watchlist", icon: "⭐" },
    { id: "screener", label: "Screener", icon: "🔍" },
  ];

  return (
    <aside
      style={{
        width: "240px",
        minWidth: "240px",
        height: "100vh",
        position: "fixed",
        left: 0,
        top: 0,
        display: "flex",
        flexDirection: "column",
        background: "var(--color-bg-secondary)",
        borderRight: "1px solid var(--border-subtle)",
        zIndex: 50,
      }}
    >
      {/* Brand */}
      <div style={{ padding: "24px 20px", display: "flex", alignItems: "center", gap: "12px" }}>
        <div
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "12px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 700,
            fontSize: "18px",
            flexShrink: 0,
            background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
          }}
        >
          F
        </div>
        <div>
          <h1 style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>
            FinContext
          </h1>
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>
            Market Intelligence
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: "0 12px", marginTop: "16px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavChange?.(item.id)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "10px 14px",
                borderRadius: "12px",
                fontSize: "14px",
                fontWeight: 500,
                border: "none",
                cursor: "pointer",
                transition: "all 0.2s",
                background: activeNav === item.id ? "rgba(99, 102, 241, 0.15)" : "transparent",
                color: activeNav === item.id ? "var(--color-accent-secondary)" : "var(--color-text-secondary)",
                borderLeft: activeNav === item.id ? "3px solid var(--color-accent-primary)" : "3px solid transparent",
              }}
            >
              <span style={{ fontSize: "18px" }}>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Live Indicator */}
      <div style={{ padding: "20px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "8px 12px",
            borderRadius: "8px",
            background: "rgba(16, 185, 129, 0.1)",
          }}
        >
          <span
            className="pulse-dot"
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: "var(--color-accent-green)",
              display: "inline-block",
            }}
          />
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--color-accent-green)" }}>
            Market Open
          </span>
        </div>
      </div>
    </aside>
  );
}
