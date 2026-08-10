# FinContext MCP Server

A local, stdio-transport [MCP](https://modelcontextprotocol.io) server exposing two
read-only FinContext tools to Claude Desktop, Cursor, or any other MCP host:

- **`pre_trade_check(ticker)`** — six-factor deterministic checklist (RSI, distance
  from 20-DMA, volume, valuation vs sector, 52-week range, trend). No LLM call.
- **`get_stock_context(ticker)`** — grounded snapshot + sector-peer benchmark +
  rule-based signals + news, the same context block FinContext's own Deep Dive
  is built from. No LLM call, no narrative — source material for the host
  model's own synthesis.

Both are thin wrappers over the FinContext backend's `/api/analysis/pre-trade-check`
and `/api/analysis/context` routes — no domain logic lives in this package. See
`server.py`'s module docstring for the compliance rules that shaped the tool
descriptions; don't loosen that language without reading it first.

## Why this exists

This is the "free, top-of-funnel distribution channel" half of the MCP viability
assessment for FinContext — not a replacement for the hosted web product. See
the plan doc for the full reasoning (audience mismatch, no billing rail, why
portfolio-aware flows don't fit a stateless tool). Ship this alongside the web
app, not instead of it.

## Setup

1. **Have a FinContext backend running and reachable.** Either the deployed
   instance, or locally:
   ```bash
   cd ../backend
   venv\Scripts\activate   # Windows; source venv/bin/activate on macOS/Linux
   uvicorn app.main:app --reload --port 8000
   ```

2. **Install this package's dependencies** (separate venv recommended — this
   is a standalone package, not part of the backend's requirements):
   ```bash
   cd mcp-server
   python -m venv venv
   venv\Scripts\activate      # Windows
   pip install -r requirements.txt
   ```

3. **Configure.** Copy `.env.example` to `.env` and set `FINCONTEXT_API_BASE`
   (defaults to `http://localhost:8000` if unset). `FINCONTEXT_API_KEY` is
   optional — only useful once the backend has `FINCONTEXT_API_KEYS` set.

4. **Smoke-test it runs:**
   ```bash
   python server.py
   ```
   It will sit waiting on stdin — that's correct for stdio transport. Ctrl+C
   to stop. To actually exercise it interactively before wiring into a host,
   use the MCP Inspector: `mcp dev server.py` (installed via `mcp[cli]`).

## Wire it into an MCP host

**Claude Desktop** — edit `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`;
macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "fincontext": {
      "command": "C:\\path\\to\\project1\\mcp-server\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\project1\\mcp-server\\server.py"],
      "env": {
        "FINCONTEXT_API_BASE": "https://fin-context.vercel.app/_/backend"
      }
    }
  }
}
```

Use the venv's own `python.exe`/`python` (not a bare `python` on PATH) so the
`mcp`/`httpx` install above is actually the one that runs. Restart Claude
Desktop after editing.

**Cursor** — same shape, under `mcpServers` in Cursor's MCP settings
(Settings → MCP → Add new global MCP server).

## What this deliberately does not do

- No portfolio-aware tools (Morning Brief, News Feed, Movers) — those need
  user holdings and stream over SSE; they don't fit a stateless request/response
  MCP tool. Ticker-in, context-out only.
- No billing, no user accounts. `FINCONTEXT_API_KEY` maps to the backend's
  rate-limit tier, not a real per-user subscription — see
  `backend/app/core/rate_limit.py`.
- No narrative synthesis. Both tools return structured data; the host model
  does the writing. Keep it that way — see the compliance note in `server.py`.
