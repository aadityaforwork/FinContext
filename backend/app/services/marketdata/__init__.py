"""
Raw market, company and news/policy data feeds.

Everything here talks to something outside the app (yfinance, RSS,
scrapers) and returns plain data. Nothing here knows about users,
portfolios or LLMs. `yf_safe` is the rate-limited/retrying yfinance
wrapper every other module in here goes through.
"""
