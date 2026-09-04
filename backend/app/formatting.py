"""Single shared currency-formatting utility.

Every user-facing message anywhere in the backend that states a rupee
amount -- negotiation trace lines, TrustGuard rejection/escalation reasons,
anything that can end up rendered verbatim in the dashboard (the Decision
Trace panel in particular shows raw backend reason text by design, see
frontend/src/lib/rules.js) -- goes through this one function. This bug
(a raw paise integer leaking into text a person reads as rupees) has been
found and fixed piecemeal several times before; routing every call site
through one function is what stops it from quietly reappearing in a new
file. See docs/DECISIONS.md for that history.
"""
from __future__ import annotations


def format_rupees(paise: int) -> str:
    """Converts a paise amount into the one rupee string this whole backend
    uses for user-facing text: `₹1,234.56`."""
    return f"₹{paise / 100:,.2f}"
