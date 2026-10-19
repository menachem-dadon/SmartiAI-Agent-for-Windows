const labels: Record<string, string> = {
  connected: "מחובר", configured: "מוגדר", disconnected: "לא מחובר", not_connected: "לא מחובר",
  unchecked: "טרם נבדק", login_in_progress: "בודק…", running: "בודק…", cancelled: "לא מחובר",
  account_ineligible: "נדרש מנוי", missing_dependency: "רכיב חסר", reauth_required: "החיבור פג",
};

export function ProviderConnectionStatus({ state = "unchecked", busy = false }: { state?: string; busy?: boolean }) {
  const connected = state === "connected";
  return <span className={`provider-connection-status ${connected ? "is-connected" : ""}`} role="status">
    <i aria-hidden="true" />{busy ? "בודק…" : labels[state] || "לא מחובר"}
  </span>;
}
