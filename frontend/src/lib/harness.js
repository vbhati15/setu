// Loads the real Day-4-Part-2 scenario harness output (a genuine run against
// the live Render deployment, logged as one JSON line per HTTP call) --
// see backend/app/scripts/scenario_harness.py. Nothing here is synthesized;
// this is a static copy of that run's own artifacts.
const HARNESS_BASE = "/harness";
const RUN_ID = "run_20260904-021007";

export async function loadHarnessSummary() {
  const res = await fetch(`${HARNESS_BASE}/${RUN_ID}_summary.json`);
  if (!res.ok) throw new Error(`harness summary -> HTTP ${res.status}`);
  return res.json();
}

export async function loadHarnessRecords() {
  const res = await fetch(`${HARNESS_BASE}/${RUN_ID}.jsonl`);
  if (!res.ok) throw new Error(`harness log -> HTTP ${res.status}`);
  const text = await res.text();
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line));
}

// Groups a negotiate response's flat trace (one entry per speaker per round)
// into one row per round, deriving which side conceded and by how much from
// the actual offer numbers -- no assumed opening formula, just the deltas
// between consecutive rounds' real offers.
export function groupRoundsFromTrace(trace) {
  const byRound = new Map();
  for (const t of trace) {
    if (t.round === 0) continue;
    if (!byRound.has(t.round)) byRound.set(t.round, { round: t.round, messages: [] });
    const r = byRound.get(t.round);
    if (t.buyer_offer_paise != null) r.buyer_offer_paise = t.buyer_offer_paise;
    if (t.merchant_offer_paise != null) r.merchant_offer_paise = t.merchant_offer_paise;
    r.buyer_risk = t.buyer_risk;
    r.merchant_risk = t.merchant_risk;
    r.messages.push({ speaker: t.speaker, message: t.message });
  }
  const rounds = [...byRound.values()].sort((a, b) => a.round - b.round);

  let prevBuyer = null;
  let prevMerchant = null;
  for (const r of rounds) {
    const haveOffers = r.buyer_offer_paise != null && r.merchant_offer_paise != null;
    if (!haveOffers || prevBuyer === null) {
      r.conceder = null;
      r.concessionPaise = null;
    } else {
      const dBuyer = r.buyer_offer_paise - prevBuyer;
      const dMerchant = r.merchant_offer_paise - prevMerchant;
      if (Math.abs(dBuyer) >= Math.abs(dMerchant) && dBuyer !== 0) {
        r.conceder = "buyer";
        r.concessionPaise = Math.abs(dBuyer);
      } else if (dMerchant !== 0) {
        r.conceder = "merchant";
        r.concessionPaise = Math.abs(dMerchant);
      } else {
        r.conceder = null;
        r.concessionPaise = 0;
      }
    }
    if (haveOffers) {
      prevBuyer = r.buyer_offer_paise;
      prevMerchant = r.merchant_offer_paise;
    }
  }
  return rounds;
}

export function hasRiskTelemetry(trace) {
  return Array.isArray(trace) && trace.some((t) => t.buyer_risk !== undefined && t.buyer_risk !== null);
}
