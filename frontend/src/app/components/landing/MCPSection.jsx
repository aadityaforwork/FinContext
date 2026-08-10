"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * MCPSection — F3 tabular spec sheet (the previous build used F4 step
 * sequence for HowItWorks, so the archetype rotates within the page).
 *
 * Built as a hairline-ruled grid rather than a literal <table>: the F3
 * voice is rows + columns + hairlines + tabular figures, and a grid
 * collapses to a stacked key/value layout on phones without the usual
 * `display: block` table-stacking hacks. Two tools is also below the size
 * where a real <table> earns its semantics.
 *
 * HONEST COPY — everything here is checked against mcp-server/server.py and
 * mcp-server/README.md:
 *   · the two tool names and their signatures
 *   · "no LLM" — both tools are thin HTTP wrappers over deterministic
 *     backend routes; neither calls a model
 *   · the six pre-trade factors, verbatim from the tool's own docstring
 *   · the config snippet, which is the README's Claude Desktop block
 *   · the anonymous rate limit (30/min per IP, backend/app/core/rate_limit.py)
 * No usage numbers, no install counts, no "trusted by" — none exist yet, and
 * an invented one would undo the point the rest of the page is making.
 *
 * The compliance line is not decoration: the tool docstrings really are the
 * only lever this server has over how a host model phrases its answer, which
 * is worth saying out loud to the audience most likely to care.
 */

const TOOLS = [
  {
    name: "pre_trade_check",
    arg: "ticker",
    returns:
      "Six checks, each PASS / CAUTION / FAIL against a fixed rule: RSI, distance from the 20-day moving average, volume vs its 20-day average, valuation against the sector peer median, position in the 52-week range, and trend vs the 50-day moving average.",
    compute: "No LLM",
  },
  {
    name: "get_stock_context",
    arg: "ticker",
    returns:
      "The full context block — snapshot, peer benchmark, scores, rule-based signals, same-sector alternatives, and recent news. The same object the app itself is built from, unmodified.",
    compute: "No LLM",
  },
];

const CONFIG = `{
  "mcpServers": {
    "fincontext": {
      "command": "/path/to/mcp-server/venv/bin/python",
      "args": ["/path/to/mcp-server/server.py"],
      "env": {
        "FINCONTEXT_API_BASE": "https://fin-context.vercel.app/_/backend"
      }
    }
  }
}`;

export default function MCPSection() {
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(CONFIG);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the snippet is selectable, so no toast, no noise */
    }
  }, []);

  return (
    <section id="mcp" className="landing-section">
      <div className="mcp__head">
        <h2 className="landing-h2">Point your agent at it</h2>
        <p className="landing-lede">
          The same grounded context is exposed as an MCP server — two
          read-only tools, no model in the loop on our side. Your agent asks
          for a ticker and gets structured data back to reason over, rather
          than someone else&rsquo;s conclusion to repeat.
        </p>
      </div>

      <div className="mcp__spec">
        <div className="mcp__spec-head" aria-hidden="true">
          <span>Tool</span>
          <span>Returns</span>
          <span>Compute</span>
        </div>
        {TOOLS.map((t) => (
          <div key={t.name} className="mcp__spec-row">
            <div className="mcp__tool">
              <code className="mcp__tool-name">{t.name}</code>
              <span className="mcp__tool-arg">({t.arg})</span>
            </div>
            <p className="mcp__tool-returns">{t.returns}</p>
            <span className="mcp__tool-compute">{t.compute}</span>
          </div>
        ))}
      </div>

      <div className="mcp__grid">
        <div className="mcp__install">
          <div className="mcp__frame-top">
            <span className="mcp__frame-label">claude_desktop_config.json</span>
            <button
              type="button"
              className="mcp__copy"
              onClick={copy}
              data-state={copied ? "copied" : "idle"}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="mcp__code">
            <code>{CONFIG}</code>
          </pre>
          <p className="mcp__frame-foot">
            Same shape in Cursor&rsquo;s MCP settings, or any other MCP host —
            it&rsquo;s stdio transport, nothing bespoke.
          </p>
        </div>

        <aside className="mcp__aside">
          <div className="mcp__aside-block">
            <h3 className="mcp__aside-title">Read-only, by design</h3>
            <p className="mcp__aside-body">
              Ticker in, context out. No portfolio access, no holdings, no
              writes — the agent surface can&rsquo;t touch an account.
            </p>
          </div>
          <div className="mcp__aside-block">
            <h3 className="mcp__aside-title">Free to point at</h3>
            <p className="mcp__aside-body">
              No key needed to start; anonymous callers get 30 requests a
              minute. An API key raises that ceiling when you need it.
            </p>
          </div>
          <div className="mcp__aside-block">
            <h3 className="mcp__aside-title">Compliance travels with the tool</h3>
            <p className="mcp__aside-body">
              Each tool&rsquo;s description tells the calling model to present
              the factors and not compress them into a buy or sell call — the
              one lever we have over how a host phrases its answer.
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
