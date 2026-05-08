"use client";

export default function BrandedSplash({ message = "Loading your dashboard…" }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "20px",
        background:
          "radial-gradient(1200px 600px at 50% -10%, rgba(99,102,241,0.12), transparent 70%), var(--color-bg-primary)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div
          style={{
            width: "44px",
            height: "44px",
            borderRadius: "12px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 700,
            fontSize: "20px",
            background:
              "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
            boxShadow: "0 0 30px rgba(99, 102, 241, 0.35)",
          }}
        >
          F
        </div>
        <div>
          <div
            className="gradient-text"
            style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-0.01em" }}
          >
            FinContext
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
            Market Intelligence
          </div>
        </div>
      </div>

      <Spinner />

      <p style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>{message}</p>
    </div>
  );
}

function Spinner() {
  return (
    <>
      <style>{`
        @keyframes fc-spinner-rotate { to { transform: rotate(360deg); } }
        @keyframes fc-spinner-dash {
          0%   { stroke-dasharray: 1, 120; stroke-dashoffset: 0; }
          50%  { stroke-dasharray: 70, 120; stroke-dashoffset: -20; }
          100% { stroke-dasharray: 70, 120; stroke-dashoffset: -90; }
        }
      `}</style>
      <svg
        width="36"
        height="36"
        viewBox="0 0 50 50"
        style={{ animation: "fc-spinner-rotate 1.4s linear infinite" }}
        aria-label="Loading"
      >
        <circle
          cx="25"
          cy="25"
          r="20"
          fill="none"
          stroke="var(--color-accent-primary)"
          strokeWidth="3"
          strokeLinecap="round"
          style={{ animation: "fc-spinner-dash 1.4s ease-in-out infinite" }}
        />
      </svg>
    </>
  );
}
