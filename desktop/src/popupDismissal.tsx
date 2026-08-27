import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type {
  DetailsHTMLAttributes,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  RefObject,
} from "react";

type PopupRoot = RefObject<HTMLElement | null>;

function eventIsInside(event: Event, roots: PopupRoot[]) {
  const path = event.composedPath?.() || [];
  return roots.some((root) => {
    const element = root.current;
    if (!element) return false;
    if (path.includes(element)) return true;
    return event.target instanceof Node && element.contains(event.target);
  });
}

export function useDismissiblePopup({
  open,
  roots,
  onDismiss,
}: {
  open: boolean;
  roots: PopupRoot[];
  onDismiss: () => void;
}) {
  const rootsRef = useRef(roots);
  const dismissRef = useRef(onDismiss);
  rootsRef.current = roots;
  dismissRef.current = onDismiss;

  useEffect(() => {
    if (!open) return;
    const dismissOutside = (event: PointerEvent) => {
      if (!eventIsInside(event, rootsRef.current)) dismissRef.current();
    };
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      dismissRef.current();
      rootsRef.current[0]?.current
        ?.querySelector<HTMLElement>("summary, [aria-haspopup]")
        ?.focus();
    };
    const dismissOnWindowBlur = () => dismissRef.current();
    document.addEventListener("pointerdown", dismissOutside, true);
    document.addEventListener("keydown", dismissOnEscape, true);
    window.addEventListener("blur", dismissOnWindowBlur);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside, true);
      document.removeEventListener("keydown", dismissOnEscape, true);
      window.removeEventListener("blur", dismissOnWindowBlur);
    };
  }, [open]);
}

export const DismissibleDetails = forwardRef<
  HTMLDetailsElement,
  DetailsHTMLAttributes<HTMLDetailsElement>
>(function DismissibleDetails(
  { onClick, onKeyDown, onToggle, ...props },
  forwardedRef,
) {
  const detailsRef = useRef<HTMLDetailsElement | null>(null);
  const [open, setOpen] = useState(Boolean(props.open));
  useImperativeHandle(forwardedRef, () => detailsRef.current!, []);
  useDismissiblePopup({
    open,
    roots: [detailsRef],
    onDismiss: () => {
      if (detailsRef.current) detailsRef.current.open = false;
      setOpen(false);
    },
  });

  const keyDown = (event: ReactKeyboardEvent<HTMLDetailsElement>) => {
    onKeyDown?.(event);
  };
  const click = (event: ReactMouseEvent<HTMLDetailsElement>) => {
    const target = event.target;
    const summary = target instanceof Element ? target.closest("summary") : null;
    const details = detailsRef.current;
    if (details && summary?.parentElement === details) {
      setOpen(!details.open);
    }
    onClick?.(event);
  };

  return (
    <details
      {...props}
      ref={detailsRef}
      onClick={click}
      onKeyDown={keyDown}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
        onToggle?.(event);
      }}
    />
  );
});
