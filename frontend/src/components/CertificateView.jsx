import { motion, AnimatePresence } from "framer-motion";
import { X, Check, ShieldCheck, Stamp } from "lucide-react";
import { paise } from "../lib/rules";

// Formats the certificate's raw ISO `issued_at` the way a person reads a
// receipt date -- this is purely cosmetic; verify_certificate.py still
// checks the original ISO string inside the certificate JSON, untouched.
function formatIssuedAt(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", {
    dateStyle: "long",
    timeStyle: "short",
  });
}

// Purely a human-readable rendering of the same certificate object the
// "Download verification certificate" button already serializes verbatim --
// no field here is computed differently, nothing is re-signed or re-verified.
export default function CertificateView({ certificate, onClose }) {
  if (!certificate) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.97 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          onClick={(e) => e.stopPropagation()}
          className="relative w-full max-w-lg rounded-2xl border-2 border-gold-500/50 bg-ink-900 p-1 shadow-2xl"
        >
          <div className="rounded-xl border border-gold-500/25 bg-ink-950/60 p-6 sm:p-8">
            <button
              onClick={onClose}
              aria-label="Close certificate"
              className="absolute top-4 right-4 text-parchment-500 hover:text-parchment-100 transition-colors"
            >
              <X size={18} />
            </button>

            <div className="flex flex-col items-center text-center mb-6">
              <div className="w-12 h-12 rounded-full bg-gold-500/15 border border-gold-500/40 flex items-center justify-center mb-3">
                <Stamp size={22} className="text-gold-400" />
              </div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-parchment-500">
                Certificate of Verified Purchase
              </div>
            </div>

            <div className="text-center mb-6">
              <div className="text-lg sm:text-xl font-semibold text-parchment-100">
                {certificate.product?.name}
              </div>
              <div className="text-3xl font-bold text-gold-400 mt-1">
                {paise(certificate.agreed_price_paise)}
              </div>
            </div>

            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm mb-6 border-t border-b border-ink-700 py-4">
              <dt className="text-parchment-500">Transaction ID</dt>
              <dd className="text-parchment-100 font-mono text-right break-all">{certificate.transaction_id}</dd>
              <dt className="text-parchment-500">Issued</dt>
              <dd className="text-parchment-100 text-right">{formatIssuedAt(certificate.issued_at)}</dd>
              <dt className="text-parchment-500">Issuer</dt>
              <dd className="text-parchment-100 text-right">{certificate.issuer}</dd>
            </dl>

            <div className="mb-6">
              <div className="text-xs font-medium uppercase tracking-wide text-parchment-500 mb-2">
                Trust checks passed
              </div>
              <ul className="space-y-1.5">
                {(certificate.trust_checks_passed || []).map((check) => (
                  <li key={check} className="flex items-start gap-2.5 text-sm text-parchment-300">
                    <Check size={14} className="text-gold-400 shrink-0 mt-0.5" />
                    <span>{check}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex items-center justify-center gap-1.5 text-[11px] text-parchment-500">
              <ShieldCheck size={13} className="text-gold-500" />
              Signed with Ed25519 — verifiable offline, no server trust required
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
