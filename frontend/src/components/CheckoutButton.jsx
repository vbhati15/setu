import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, CreditCard, CheckCircle2, XCircle } from "lucide-react";
import { postCreateCheckoutOrder, postConfirmCheckout } from "../api";
import { paise } from "../lib/rules";

const RAZORPAY_SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = RAZORPAY_SCRIPT_SRC;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("couldn't load Razorpay Checkout"));
    document.body.appendChild(script);
  });
}

// Hands the agreed price off to a real human: a real Razorpay test-mode
// order (see POST /checkout/order) opened in the visitor's own browser via
// the official Checkout widget -- not automated, since a script driving
// that widget's own form is exactly what trips Razorpay's bot detection
// (see docs/DECISIONS.md, 2026-09-02 and 2026-09-05). This component only
// ever opens the widget and reports back what the visitor themselves did.
export default function CheckoutButton({ checkoutToken, productName, pricePaise, onSuccess }) {
  const [state, setState] = useState("idle"); // idle | opening | paying | success | failed | cancelled
  const [error, setError] = useState(null);
  const [transactionId, setTransactionId] = useState(null);

  async function startCheckout() {
    setState("opening");
    setError(null);
    try {
      await loadRazorpayScript();
      const order = await postCreateCheckoutOrder(checkoutToken);
      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount_paise,
        currency: order.currency,
        order_id: order.order_id,
        name: "Setu",
        description: order.product_name || productName,
        prefill: { email: "buyer@setu.dev", contact: "9999999999" },
        handler: async (response) => {
          setState("paying");
          try {
            const result = await postConfirmCheckout(checkoutToken, response);
            setTransactionId(result.transaction);
            setState("success");
            onSuccess?.(result);
          } catch (e) {
            setError(e.message);
            setState("failed");
          }
        },
        modal: {
          ondismiss: () => setState((s) => (s === "opening" ? "cancelled" : s)),
        },
      });
      rzp.on("payment.failed", (response) => {
        setError(response.error?.description || "payment failed");
        setState("failed");
      });
      rzp.open();
    } catch (e) {
      setError(e.message);
      setState("failed");
    }
  }

  if (state === "success") {
    return (
      <div className="mt-3 flex items-center gap-2 text-sm text-gold-300">
        <CheckCircle2 size={16} className="shrink-0" />
        Payment confirmed — transaction <span className="font-mono">{transactionId}</span>
      </div>
    );
  }

  const busy = state === "opening" || state === "paying";

  return (
    <div className="mt-3">
      <motion.button
        onClick={startCheckout}
        disabled={busy}
        whileHover={!busy ? { scale: 1.02 } : {}}
        whileTap={!busy ? { scale: 0.98 } : {}}
        className="inline-flex items-center gap-2 rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-gold-400 shadow-lg shadow-gold-500/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {busy ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            {state === "paying" ? "Confirming payment…" : "Opening checkout…"}
          </>
        ) : (
          <>
            <CreditCard size={14} />
            Complete your purchase — {paise(pricePaise)}
          </>
        )}
      </motion.button>

      {(state === "failed" || state === "cancelled") && (
        <div className="mt-2 flex items-center gap-2 text-xs text-parchment-500">
          <XCircle size={13} className={state === "failed" ? "text-red-400" : "text-parchment-500"} />
          {state === "cancelled"
            ? "Checkout closed — no charge was made. You can try again whenever you're ready."
            : `Payment didn't go through${error ? ` (${error})` : ""} — you can try again.`}
        </div>
      )}
    </div>
  );
}
