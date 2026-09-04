import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Power, AlertTriangle, Loader2 } from "lucide-react";
import { getKillSwitchStatus, activateKillSwitch, deactivateKillSwitch } from "../api";

export default function KillSwitch() {
  const [status, setStatus] = useState(null);
  const [adminKey, setAdminKey] = useState("");
  const [reason, setReason] = useState("Activated manually from the dashboard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [confirming, setConfirming] = useState(false);

  async function refresh() {
    try {
      setStatus(await getKillSwitchStatus());
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, []);

  async function handleActivate() {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setStatus(await activateKillSwitch(adminKey, reason));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  async function handleDeactivate() {
    setBusy(true);
    setError(null);
    try {
      setStatus(await deactivateKillSwitch(adminKey));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const active = status?.active;

  return (
    <div className="relative w-full overflow-hidden">
      {active && (
        <motion.div
          className="pointer-events-none absolute inset-0"
          animate={{
            background: [
              "radial-gradient(circle at 20% 50%, rgba(200,82,74,0.16) 0%, rgba(200,82,74,0.06) 35%, transparent 70%)",
              "radial-gradient(circle at 20% 50%, rgba(200,82,74,0.26) 0%, rgba(200,82,74,0.10) 35%, transparent 70%)",
              "radial-gradient(circle at 20% 50%, rgba(200,82,74,0.16) 0%, rgba(200,82,74,0.06) 35%, transparent 70%)",
            ],
          }}
          style={{ filter: "blur(40px)" }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        />
      )}

      <div className="relative grid lg:grid-cols-[1.1fr_1fr] gap-8 items-center">
        <div>
          <h2 className="text-2xl sm:text-3xl font-semibold text-parchment-100 flex items-center gap-3 mb-2">
            <Power size={24} className={active ? "text-red-400" : "text-gold-400"} />
            Kill switch
          </h2>
          <p className="text-sm text-parchment-400 leading-relaxed max-w-lg">
            One switch, complete control. If something looks wrong, this instantly stops every new
            transaction — no exceptions, no delay. This isn't a demo toggle — it's connected to the real,
            live system.
          </p>

          <motion.div
            animate={
              active
                ? {
                    boxShadow: [
                      "0 0 0px rgba(200,82,74,0)",
                      "0 0 40px rgba(200,82,74,0.3)",
                      "0 0 0px rgba(200,82,74,0)",
                    ],
                  }
                : {}
            }
            transition={{ duration: 2, repeat: active ? Infinity : 0 }}
            className={`mt-5 rounded-xl border p-5 ${
              active ? "border-red-900/60 bg-red-950/20" : "border-ink-700 bg-ink-900/50"
            }`}
          >
            <AnimatePresence mode="wait">
              <motion.div
                key={active ? "active" : "inactive"}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className={`font-mono text-lg sm:text-xl tracking-tight ${
                  active ? "text-red-300" : "text-gold-400"
                }`}
              >
                {status ? (active ? "ACTIVE — transactions halted" : "INACTIVE — accepting transactions") : "loading…"}
              </motion.div>
            </AnimatePresence>
            {status?.reason && (
              <div className="text-sm text-parchment-500 mt-2 font-mono">reason: {status.reason}</div>
            )}
          </motion.div>
        </div>

        <div className="rounded-xl border border-ink-700 bg-ink-900/40 p-5 sm:p-6 space-y-3">
          <div className="text-xs font-mono uppercase tracking-wide text-parchment-500">Admin controls</div>
          <input
            type="password"
            placeholder="X-ADMIN-KEY"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            className="w-full rounded-md border border-ink-700 bg-ink-950 px-4 py-2.5 text-sm font-mono text-parchment-100 placeholder:text-parchment-500 focus:outline-none focus:border-gold-500/50"
          />

          {!active && (
            <input
              type="text"
              placeholder="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full rounded-md border border-ink-700 bg-ink-950 px-4 py-2.5 text-sm text-parchment-100 placeholder:text-parchment-500 focus:outline-none focus:border-gold-500/50"
            />
          )}

          {error && (
            <div className="text-xs font-mono text-red-400 flex items-center gap-1.5">
              <AlertTriangle size={13} /> {error}
            </div>
          )}

          <div className="flex flex-wrap gap-3 pt-2">
            {active ? (
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleDeactivate}
                disabled={busy || !adminKey}
                className="inline-flex items-center gap-2 rounded-md border border-gold-500/40 bg-gold-500/10 px-5 py-2.5 text-sm font-medium text-gold-300 hover:bg-gold-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {busy && <Loader2 size={14} className="animate-spin" />} Deactivate
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleActivate}
                disabled={busy || !adminKey}
                className={`inline-flex items-center gap-2 rounded-md border px-5 py-2.5 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed ${
                  confirming
                    ? "border-red-500/70 bg-red-500/20 text-red-300"
                    : "border-red-900/50 bg-red-950/30 text-red-400 hover:bg-red-950/50"
                }`}
              >
                {busy && <Loader2 size={14} className="animate-spin" />}
                {confirming ? "Click again to confirm" : "Activate kill switch"}
              </motion.button>
            )}
            {confirming && (
              <button
                onClick={() => setConfirming(false)}
                className="text-sm text-parchment-500 hover:text-parchment-300"
              >
                cancel
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
