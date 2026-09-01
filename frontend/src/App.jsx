export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center px-6">
      <div className="max-w-xl text-center space-y-4">
        <h1 className="text-4xl font-bold tracking-tight">Setu</h1>
        <p className="text-slate-400">
          Agent-to-Agent Commerce Gateway — dashboard placeholder. Negotiation
          traces, transaction history, and policy controls land here as the
          Buyer Agent and bargaining layer come online.
        </p>
        <div className="text-sm text-slate-500">
          Backend health: <code>GET /health</code> on the FastAPI service.
        </div>
      </div>
    </div>
  );
}
