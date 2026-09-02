// VITE_API_URL points at the deployed backend (e.g. https://setu-api.up.railway.app).
// Falls back to "/api", which vite.config.js proxies to localhost:8001 in dev.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

async function getJSON(path) {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`);
  }
  return res.json();
}

export function getHealth() {
  return getJSON("/health");
}

export function getCatalog() {
  return getJSON("/catalog");
}
