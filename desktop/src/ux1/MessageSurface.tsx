import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

// A candidate composition slot before the source renderer's actions. React
// still owns every handler and reference; the source renderer is unmodified.
export function MessageSurface({ children, references, role, enter }: { children: ReactNode; references?: ReactNode; role: string; enter?: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const hasReferences = !!references;
  useLayoutEffect(() => {
    if (!hasReferences) return;
    const actions = root.current?.querySelector(':scope > .chat-message-row > .message-actions');
    if (!actions) return;
    const host = document.createElement('div');
    host.className = 'ux-message-references-slot';
    actions.before(host);
    setSlot(host);
    return () => host.remove();
  }, [hasReferences]);
  return <div ref={root} className={`ux-message ux-${role}`} data-enter={enter || undefined}>{children}{slot && references && createPortal(references, slot)}</div>;
}
