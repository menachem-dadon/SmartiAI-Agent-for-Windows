import { Component, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { Alert, Button, DesignSystemProvider } from "./design-system";
import { type ResolvedTheme } from "./designSystem";
import { setStartupVisible, startupTheme } from "./startup";

function Surface({ children, theme = startupTheme() }: { children: ReactNode; theme?: ResolvedTheme }) {
  useLayoutEffect(() => { setStartupVisible(false); }, []);
  return <DesignSystemProvider theme={theme} className="interface-recovery"><main dir="rtl">{children}</main></DesignSystemProvider>;
}

export function InterfaceLoading() {
  const delayed = useStartupWatchdog(true);
  return delayed ? <Surface><StartupRecovery /></Surface> : null;
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

export function StartupRecovery({ failed = false }: { failed?: boolean }) {
  return <Alert tone={failed ? "danger" : "warning"} title={failed ? "הממשק לא נטען" : "טעינת הממשק מתעכבת"}><p>אפשר לטעון את הממשק מחדש בלי להפעיל את מנוע העבודה מחדש.</p><Button onClick={() => window.location.reload()}>טעינת הממשק מחדש</Button></Alert>;
}

export function StartupFailure({ theme, failed }: { theme: ResolvedTheme; failed: boolean }) {
  return <Surface theme={theme}><StartupRecovery failed={failed} /></Surface>;
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
