import { Component, useEffect, useState, type ReactNode } from "react";
import { Alert, Button, DesignSystemProvider, LoadingState } from "./design-system";
import { resolveTheme } from "./designSystem";

function Surface({ children }: { children: ReactNode }) {
  return <DesignSystemProvider theme={resolveTheme("system", window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false)} className="interface-recovery"><main dir="rtl">{children}</main></DesignSystemProvider>;
}

export function InterfaceLoading() {
  return <Surface><LoadingState label="פותח את סמארטי" /></Surface>;
}

export function useStartupWatchdog(pending: boolean) {
  const [delayed, setDelayed] = useState(false);
  useEffect(() => {
    setDelayed(false);
    if (!pending) return;
    const timer = window.setTimeout(() => setDelayed(true), 15000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  return pending && delayed;
}

export function StartupRecovery() {
  return <Alert tone="warning" title="טעינת הממשק מתעכבת"><p>מנוע העבודה מחובר. אפשר לטעון את הממשק מחדש בלי להפעיל את המנוע מחדש.</p><Button onClick={() => window.location.reload()}>טעינת הממשק מחדש</Button></Alert>;
}

// Covers module-load and React render failures. Core and its background owners
// remain in Rust; only an explicit user reload retries the interface.
export class InterfaceRecovery extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) {
    // Never serialize exception messages, stacks, account values or draft text.
    console.error("Smarti interface failed", { type: error.name });
  }
  render() {
    return this.state.failed
      ? <Surface><Alert tone="danger" title="הממשק לא נטען"><p>אפשר לטעון את הממשק מחדש. הפעילות ברקע ממשיכה לפעול.</p><Button onClick={() => window.location.reload()}>טעינת הממשק מחדש</Button></Alert></Surface>
      : this.props.children;
  }
}
