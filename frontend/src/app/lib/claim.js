export function claimText(v) {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "object" && typeof v.text === "string") return v.text;
  return String(v);
}

export function claimSource(v) {
  if (v && typeof v === "object" && typeof v.source === "string") return v.source;
  return null;
}
