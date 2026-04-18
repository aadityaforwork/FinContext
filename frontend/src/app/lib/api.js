"use client";

/**
 * API helpers: a single source of truth for the backend URL, and a one-time
 * fetch patch so every request to our API automatically sends cookies.
 *
 * Using a global patch is pragmatic: there are ~30 fetch call sites in the app
 * and we want credentials on all of them without touching each one.
 */

// Resolve the backend URL. If NEXT_PUBLIC_API_URL is set, use it verbatim.
// Otherwise, mirror the browser's hostname so cookies stay first-party
// (localhost and 127.0.0.1 are treated as different sites by SameSite=Lax,
// which is what was causing reloads to log users out in dev).
export const API_BASE = (() => {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
})();

let _patched = false;

export function installFetchCredentials() {
  if (_patched) return;
  if (typeof window === "undefined") return;
  _patched = true;

  const origFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof Request
        ? input.url
        : String(input);

    // Only attach credentials for requests to our own backend
    if (url && url.startsWith(API_BASE)) {
      init = { ...init, credentials: init.credentials ?? "include" };
    }
    return origFetch(input, init);
  };
}

/**
 * Thin JSON helper around fetch — used by auth pages. Always includes credentials.
 */
export async function apiJson(path, { method = "GET", body, headers } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // non-JSON response
  }

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) ||
      `Request failed: ${res.status}`;
    const err = new Error(typeof message === "string" ? message : JSON.stringify(message));
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}
