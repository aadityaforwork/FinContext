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

---

## Telegram bot v0

Push a personalized morning brief (P&L + top movers + policy headlines) to
every linked user every weekday at 8:30 AM IST. No app open required —
this is the workflow + distribution moat.

### One-time bot creation

1. Open Telegram → search for **@BotFather**.
2. Send `/newbot` → pick a name (e.g. *FinContext*) → pick a username ending
   in `bot` (e.g. `FinContextBot` or `FinContextDailyBot`).
3. BotFather replies with a token like `123456789:ABCdef-very-long-token`.
   Save it — that's `TELEGRAM_BOT_TOKEN`.

### One-time server setup

On Render → your backend service → **Environment** → add three vars:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | a random string (`python -c "import secrets; print(secrets.token_urlsafe(24))"`) |
| `WEB_APP_URL` | your deployed frontend, e.g. `https://fincontext.app` |

`ADMIN_TOKEN` is shared with the outcomes cron — already set if you've done
that step.

Then run **migration 006** in Supabase (`supabase/migrations/006_telegram_links.sql`).

### One-time webhook registration

Tell Telegram where to POST incoming messages. Run this once after the env
vars are set and the backend has redeployed (replace placeholders):

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://YOUR-BACKEND.onrender.com/api/telegram/webhook",
        "secret_token": "<YOUR_TELEGRAM_WEBHOOK_SECRET>",
        "drop_pending_updates": true
      }'
```

Expected response:
```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

Verify:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

### Frontend env var

In your Vercel project (or `.env.local` for dev), add:

```
NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=FinContextBot
```

(without the `@`, just the username). This is the deep-link the Settings page
uses to open the bot in Telegram.

### Test the link flow end-to-end

1. Sign in to the web app → **Settings** → "Daily brief on Telegram" → click
   **Generate link code**. Copy the 6-character code.
2. Open `https://t.me/<your_bot_username>` in a browser or Telegram → press
   **Start**.
3. Send `/link CODE` (replace CODE with what you copied). The bot should reply
   `✅ Linked!`.
4. Go back to Settings → click **I've sent it — refresh** (or reload). The
   section should now show `Connected · @yourusername`.

### Daily brief cron

The brief job needs to run **once per trading day at ~8:30 AM IST = 3:00 UTC**.

#### Option A — cron-job.org (free, recommended)

1. Sign in at https://cron-job.org → **Create cronjob**.
2. Fill in:
   - **Title:** `FinContext daily brief`
   - **URL:** `https://YOUR-BACKEND.onrender.com/api/telegram/send-daily-brief`
   - **Schedule:** Custom cron `0 3 * * 1-5` (3:00 UTC, Mon–Fri)
   - **Advanced:**
     - Method: **POST**
     - Timeout: **300 seconds**
     - Custom HTTP header: `X-Admin-Token` = `<your ADMIN_TOKEN>`
3. **Save**, then click **Run now** to test.

Expected response:
```json
{
  "targets": 1,
  "sent": 1,
  "skipped_no_holdings": 0,
  "failed": 0
}
```

#### Option B — local script (manual, useful for testing)

```powershell
$env:FINCONTEXT_API_BASE   = "https://YOUR-BACKEND.onrender.com"
$env:FINCONTEXT_ADMIN_TOKEN = "<your admin token>"
python scripts/send_daily_brief.py
```

### Bot commands users can send

| Command | Effect |
|---|---|
| `/start` | Welcome message + how-to |
| `/link CODE` | Bind this chat to a FinContext account (CODE from Settings) |
| `/off` | Pause daily briefs |
| `/on` | Resume daily briefs |
| `/help` | Command list |

If a user blocks the bot, Telegram returns `403 Forbidden` and the backend
auto-disables their `daily_brief_enabled` so we don't keep retrying.

### Troubleshooting

| Symptom | Cause |
|---|---|
| Webhook setup says `Wrong response from the webhook` | Backend isn't deployed yet, or `/api/telegram/webhook` returns non-2xx. Check Render logs. |
| `/link CODE` says "code isn't valid" | Code expired (10-min TTL), or it was generated for a different user. Generate a fresh one. |
| Settings page shows "Checking link status…" forever | Backend `/api/telegram/link-status` returned non-OK or Supabase JWT verification failed. Check Render logs for the user's session. |
| Daily brief returns `targets: 0` | No users have linked their Telegram yet. Try the link flow first. |
| Daily brief returns `failed > 0` with "Forbidden" | The user blocked the bot. Backend auto-disables their brief — no action needed. |
