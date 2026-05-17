/**
 * horizonPref
 * -----------
 * Tiny localStorage helper for the user's preferred analysis horizon.
 * The horizon they last picked on the Deep Dive page becomes the default
 * for every subsequent stock they click into — so a swing-trader flips once
 * and stops re-flipping for every ticker.
 *
 * Scoped per user.id (same pattern as the onboarding flags) so two accounts
 * on the same browser don't leak preferences into each other. SSR-safe —
 * returns the default when window is undefined.
 */

const VALID = new Set(["long_term", "swing"]);
const DEFAULT = "long_term";

function keyFor(userId) {
  return `fincontext_horizon_pref_${userId || "anon"}`;
}

export function getHorizonPref(userId) {
  if (typeof window === "undefined") return DEFAULT;
  try {
    const v = window.localStorage.getItem(keyFor(userId));
    return VALID.has(v) ? v : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

export function setHorizonPref(userId, value) {
  if (typeof window === "undefined") return;
  if (!VALID.has(value)) return;
  try {
    window.localStorage.setItem(keyFor(userId), value);
  } catch { /* quota / private-browsing — silently ignore */ }
}
