"use client";

export default function DashboardHeader({ onSearch }) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && e.target.value.trim()) {
      onSearch?.(e.target.value.trim());
    }
  };

  return (
    <header className="header-responsive">
      <div>
        <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>
          Dashboard
        </h2>
        <p style={{ fontSize: "13px", marginTop: "2px", color: "var(--color-text-muted)" }}>
          {today} • NSE / BSE
        </p>
      </div>

      <div className="header-actions">
        <div className="header-search" style={{ position: "relative" }}>
          <input
            type="text"
            placeholder="Search tickers..."
            onKeyDown={handleKeyDown}
            style={{
              width: "100%",
              padding: "8px 16px 8px 38px",
              borderRadius: "12px",
              fontSize: "13px",
              border: "1px solid var(--border-subtle)",
              outline: "none",
              background: "var(--color-bg-card)",
              color: "var(--color-text-primary)",
            }}
          />
          <svg
            style={{
              position: "absolute",
              left: "12px",
              top: "50%",
              transform: "translateY(-50%)",
              width: "16px",
              height: "16px",
              color: "var(--color-text-muted)",
            }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        <button
          style={{
            position: "relative",
            padding: "8px",
            borderRadius: "12px",
            background: "var(--color-bg-card)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <svg
            style={{ width: "20px", height: "20px", color: "var(--color-text-secondary)" }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>
          <span
            style={{
              position: "absolute",
              top: "-2px",
              right: "-2px",
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: "var(--color-accent-red)",
            }}
          />
        </button>

        <div
          style={{
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "14px",
            fontWeight: 700,
            color: "white",
            background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
          }}
        >
          A
        </div>
      </div>
    </header>
  );
}
