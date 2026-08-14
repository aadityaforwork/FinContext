-- =============================================================================
-- 012 — Re-grade historical outcomes against horizon-scaled hit thresholds
-- =============================================================================
-- WHY
-- ---
-- Until 2026-08-14, outcome_ledger._hit_rule compared EVERY horizon against one
-- flat 0.5% band (`HIT_THRESHOLD_PCT = 0.5`). The function didn't even take the
-- horizon as an argument. That silently broke the score in both directions:
--
--   * 'neutral' calls became near-impossible to hit as the horizon grew — a
--     stock staying inside +/-0.5% for 20 trading days basically never happens.
--     Measured on this table before the fix: 3.7% hit rate at 20d.
--   * 'positive'/'negative' calls became progressively FREE, since clearing a
--     fixed 0.5% over 20 days takes no skill. Measured: 52.7% at 20d for
--     'negative', vs 26.8% for the same direction at 5d.
--
-- The two distortions partly cancel in the headline number, which is why the
-- 1d/5d/20d rates all looked flatly similar (33/36/36%) while the per-direction
-- breakdown underneath was pulling apart. Any cross-horizon comparison — and
-- anything derived from one, including track_record.py's calibration factors
-- and miss_fixtures.py's "expected direction" — was reading a broken ruler.
--
-- The code fix is outcome_ledger.hit_threshold_pct(horizon): the base 0.5%
-- scales as sqrt(trading days), the standard random-walk volatility scaling,
-- since price dispersion grows with the square root of elapsed time.
--   1d  -> 0.5%      (unchanged; this is the base)
--   5d  -> 0.5*sqrt(5)  ~= 1.1180%
--   20d -> 0.5*sqrt(20) ~= 2.2361%
--
-- This migration applies that same rule to rows graded BEFORE the fix, so the
-- table isn't a mix of two incompatible rules. Without it, /accuracy would
-- show old rows scored one way and new rows another.
--
-- SAFETY
-- ------
-- `hit` is a pure deterministic function of (direction, return_pct, horizon),
-- all of which are stored and NOT modified here. So this is fully reversible:
-- re-running with a flat 0.5 in place of the CASE restores the old grades. No
-- prediction, price, or return value is touched — only the derived hit flag.
--
-- 'mixed'-direction rows are excluded: they are scored NULL by design (neither
-- hit nor miss) and must stay NULL.
--
-- Measured effect when written (all-time rows):
--   1d :  514 scored, 33.1% -> 33.1%   (0 rows changed — correct, 1d is the base)
--   5d :  436 scored, 36.0% -> 34.9%   (25 rows changed)
--   20d:  436 scored, 36.2% -> 33.0%   (54 rows changed)
-- Per-direction at 20d: neutral 3.7% -> 22.2%, negative 52.7% -> 38.4%,
-- positive 44.0% -> 35.6%.
--
-- Idempotent: re-running recomputes the same values from the same inputs.
-- =============================================================================

WITH src AS (
  SELECT
    o.prediction_id,
    o.horizon,
    o.return_pct,
    p.direction,
    CASE o.horizon
      WHEN '5d'  THEN 0.5 * sqrt(5)
      WHEN '20d' THEN 0.5 * sqrt(20)
      ELSE 0.5                      -- '1d' and any unknown horizon: the base
    END AS thr
  FROM public.prediction_outcomes o
  JOIN public.ai_predictions p ON p.id = o.prediction_id
  WHERE o.hit IS NOT NULL
    AND o.return_pct IS NOT NULL
    AND p.direction <> 'mixed'
)
UPDATE public.prediction_outcomes o
SET hit = (
      (src.direction = 'positive' AND src.return_pct >=  src.thr)
   OR (src.direction = 'negative' AND src.return_pct <= -src.thr)
   OR (src.direction = 'neutral'  AND abs(src.return_pct) < src.thr)
)
FROM src
WHERE src.prediction_id = o.prediction_id
  AND src.horizon = o.horizon;
