// Lets any component (e.g. a Hero badge) jump straight to a specific tab
// inside ProofTabs without prop-drilling tab state through App -- ProofTabs
// listens for this event and Hero/SectionNav just fire it before scrolling.
export function goToProofTab(tab) {
  window.dispatchEvent(new CustomEvent("setu:goto-proof-tab", { detail: { tab } }));
  document.getElementById("proof")?.scrollIntoView({ behavior: "smooth" });
}
