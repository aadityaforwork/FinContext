"""
Outbound delivery channels.

Telegram bot and transactional email for the daily brief and alerts.
Both are fire-and-forget from the caller's perspective and swallow
their own failures -- a delivery outage must never break the request
that triggered it.
"""
