"""
Per-user portfolio analytics.

Holdings-level P&L, exposure, risk and signal blending. Everything
here is user-scoped: per [[project_supabase_security_fix]] every query
underneath must filter by user_id and rely on RLS.
"""
