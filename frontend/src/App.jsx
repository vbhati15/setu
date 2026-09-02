import { useEffect, useState } from "react";
import { getCatalog, getHealth } from "./api";

export default function App() {
  const [status, setStatus] = useState("loading"); // "loading" | "ok" | "error"
  const [health, setHealth] = useState(null);
  const [catalogCount, setCatalogCount] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([getHealth(), getCatalog()])
      .then(([healthData, catalogData]) => {
        if (cancelled) return;
        setHealth(healthData);
        setCatalogCount(catalogData.length);
        setStatus("ok");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center px-6">
      <div className="max-w-xl text-center space-y-4">
        <h1 className="text-4xl font-bold tracking-tight">Setu</h1>
        <p className="text-slate-400">
          Agent-to-Agent Commerce Gateway — dashboard placeholder. Negotiation
          traces, transaction history, and policy controls land here as the
          Buyer Agent and bargaining layer come online.
        </p>

        <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm">
          {status === "loading" && (
            <span className="text-slate-400">Checking backend…</span>
          )}
          {status === "ok" && (
            <span className="text-emerald-400">
              Backend live — status: {health.status}, env: {health.env}, catalog: {catalogCount} products
            </span>
          )}
          {status === "error" && (
            <span className="text-red-400">Backend unreachable — {error}</span>
          )}
        </div>
      </div>
    </div>
  );
}
