"""
The prediction ledger and what the market said about it.

`outcome_ledger` records every forward-looking call and grades it at
1d/5d/20d against the real price. It also owns the grading rule
itself (hit_threshold_pct) -- per-ticker volatility scaled, see that
function's docstring before touching the constant. `track_record`
turns the graded history into per-segment calibration factors.

This is the source of truth the whole pathback/ package reads from.
"""
