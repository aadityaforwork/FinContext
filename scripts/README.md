# scripts/

Operational scripts for FinContext. Run these manually or wire them up to a
cron service.

---

## `compute_outcomes.py` — daily outcome scoring

Triggers `POST /api/outcomes/compute-daily` on the backend so the outcome
ledger fills in actual price moves + hit/miss flags for every prediction
whose horizon has elapsed. Idempotent — safe to re-run any time.

This is the job that turns the empty `prediction_outcomes` table into a
real track record. Without it, `/accuracy` stays blank forever.

### One-time server setup

The endpoint is gated by `ADMIN_TOKEN`. Set it on Render:

1. Generate a strong random token:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. In Render → your backend service → **Environment** → add:
   - `ADMIN_TOKEN` = `<the value from step 1>`
3. Save → Render redeploys.

If `ADMIN_TOKEN` is unset on the server, the endpoint returns
`503 ADMIN_TOKEN not configured on the server.` That's the first thing to
check if scoring stops working.

### Run it right now (one-off)

PowerShell (Windows):
```powershell
$env:FINCONTEXT_API_BASE   = "https://YOUR-BACKEND.onrender.com"
$env:FINCONTEXT_ADMIN_TOKEN = "<your admin token>"
python scripts/compute_outcomes.py
```

bash / zsh:
```bash
export FINCONTEXT_API_BASE=https://YOUR-BACKEND.onrender.com
export FINCONTEXT_ADMIN_TOKEN=<your admin token>
python scripts/compute_outcomes.py
```

Or skip the script entirely and `curl` it:
```bash
curl -X POST https://YOUR-BACKEND.onrender.com/api/outcomes/compute-daily \
  -H "X-Admin-Token: $FINCONTEXT_ADMIN_TOKEN"
```

Expected output on a healthy run:
```json
{
  "processed": 12,
  "written":   4,
  "skipped":   8,
  "by_horizon": {"1d": 4},
  "errors":    0
}
Summary: 12 pairs processed · 4 written · 8 skipped (not enough trading days yet) · 0 errors
```

`skipped` is normal — it counts (prediction, horizon) pairs whose horizon
hasn't fully elapsed yet. Each daily run picks up the new ones.

---

## Daily cron — pick one

The job needs to run **once per trading day**, after NSE closes. NSE shuts at
3:30 PM IST; we wait an hour for safety → **~4:30 PM IST = 11:00 UTC**.

### Option A — cron-job.org (free, recommended)

1. Sign up at https://cron-job.org
2. **Create cronjob** → fill in:
   - **Title:** `FinContext compute-daily`
   - **URL:** `https://YOUR-BACKEND.onrender.com/api/outcomes/compute-daily`
   - **Schedule** → tab "Common" or "Custom"
     - Custom expression: `0 11 * * 1-5`
     - = 11:00 UTC, Mon–Fri only (skip weekends since NSE is closed)
   - Expand **Advanced**:
     - **Request method:** POST
     - **Request timeout:** 300 seconds (Render free tier can cold-start slowly)
     - **Custom HTTP headers:** add one
       - Header name: `X-Admin-Token`
       - Header value: `<your ADMIN_TOKEN>`
3. **Save**.
4. Click **Run now** once to verify — the dashboard should show `200 OK` and
   the same JSON the manual script returns.

That's it. Outcomes will start populating tomorrow afternoon.

### Option B — Render Cron Jobs (paid, ~$1/mo)

Only useful if you're already on Render Starter. Add a cron service:

- **Type:** Cron Job
- **Build command:** *(none — pure script, no install needed)*
- **Command:** `python scripts/compute_outcomes.py`
- **Schedule:** `0 11 * * 1-5`
- **Environment variables:**
  - `FINCONTEXT_API_BASE` = `https://YOUR-BACKEND.onrender.com`
  - `FINCONTEXT_ADMIN_TOKEN` = `<your ADMIN_TOKEN>`

---

## Troubleshooting

| Symptom | What it means |
|---|---|
| `503 ADMIN_TOKEN not configured` | `ADMIN_TOKEN` env var missing on Render. Set it and redeploy. |
| `401 Invalid admin token` | Cron's `X-Admin-Token` header doesn't match server's `ADMIN_TOKEN`. |
| `503 Outcome ledger client unavailable` | `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` missing on Render. |
| `processed > 0, written = 0, skipped > 0` | Working correctly — predictions exist but no horizon has fully elapsed yet. Wait one trading day. |
| `errors > 0` | Check Render logs for `compute_pending_outcomes` warnings. Usually a transient yfinance hiccup; rerun. |

To verify outcomes are populating, run in the Supabase SQL editor:
```sql
select horizon, count(*) from prediction_outcomes group by horizon;
```

Once any row shows up, refresh `/accuracy` (or the **Track record** tab) — the
hit-rate will replace the "predictions logged, awaiting score" empty state.
