// VITE_API_URL points at the deployed backend (e.g. https://setu-59l6.onrender.com).
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

export async function postNegotiate(goalText, budgetPaise, productId) {
  const res = await fetch(`${API_BASE_URL}/negotiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal_text: goalText, budget_paise: budgetPaise, product_id: productId || null }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail ? JSON.stringify(body.detail) : `/negotiate -> HTTP ${res.status}`);
  }
  return body;
}

export function getKillSwitchStatus() {
  return getJSON("/admin/kill-switch");
}

async function postAdmin(path, adminKey, body) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-ADMIN-KEY": adminKey },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.detail || `${path} -> HTTP ${res.status}`);
  }
  return data;
}

export function activateKillSwitch(adminKey, reason) {
  return postAdmin("/admin/kill-switch/activate", adminKey, { reason });
}

export function deactivateKillSwitch(adminKey) {
  return postAdmin("/admin/kill-switch/deactivate", adminKey, {});
}
