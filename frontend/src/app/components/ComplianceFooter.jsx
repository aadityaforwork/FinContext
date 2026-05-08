"use client";

export default function ComplianceFooter() {
  return (
    <footer
      style={{
        marginTop: "32px",
        padding: "16px 24px",
        borderTop: "1px solid var(--border-subtle)",
        fontSize: "11px",
        lineHeight: 1.6,
        color: "var(--color-text-muted)",
        textAlign: "center",
      }}
    >
      <p style={{ maxWidth: "760px", margin: "0 auto" }}>
        <strong style={{ color: "var(--color-text-secondary)" }}>Disclaimer:</strong>{" "}
        FinContext is for informational and educational purposes only. We are not a SEBI-registered
        Research Analyst or Investment Adviser. Nothing here is investment advice, a recommendation,
        or a solicitation to buy or sell any security. Markets carry risk — please consult a
        qualified, registered adviser before making investment decisions.
      </p>
    </footer>
  );
}
