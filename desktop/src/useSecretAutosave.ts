import { useEffect, useRef, useState } from "react";

// Draft changes invalidate validation; writes are ordered so deletion cannot be
// overtaken by an earlier PUT. Refreshing safe settings never schedules a write.
export function useSecretAutosave<T>({ identity, delay, validate, persist, onSaved, onError, deleteOnEmpty = false }: {
  identity: string;
  delay: number;
  validate?: (value: string) => Promise<T>;
  persist: (value: string) => Promise<unknown>;
  onSaved: (result: T | undefined) => Promise<void>;
  onError: (reason: unknown) => void;
  deleteOnEmpty?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const writes = useRef(Promise.resolve());
  const callbacks = useRef({ validate, persist, onSaved, onError });
  callbacks.current = { validate, persist, onSaved, onError };
  const cancel = () => {
    generation.current++;
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => {
    setDraft(""); setBusy(false);
    return cancel;
  }, [identity]);
  const commit = async (value: string, revision: number) => {
    const handlers = callbacks.current;
    const current = () => generation.current === revision;
    if (!current()) return;
    setBusy(true);
    try {
      const result = value && handlers.validate ? await handlers.validate(value) : undefined;
      if (!current()) return;
      const write = writes.current.then(async () => {
        if (current()) await handlers.persist(value);
      });
      writes.current = write.catch(() => {});
      await write;
      if (!current()) return;
      setDraft("");
      await handlers.onSaved(result);
    } catch (reason) {
      if (current()) handlers.onError(reason);
    } finally {
      if (current()) setBusy(false);
    }
  };
  const edit = (next: string) => {
    cancel(); setDraft(next); setBusy(false);
    if (!next.trim() && !deleteOnEmpty) return;
    const revision = generation.current;
    timer.current = setTimeout(() => { timer.current = null; void commit(next.trim(), revision); }, delay);
  };
  const flush = () => {
    if (timer.current === null) return;
    clearTimeout(timer.current); timer.current = null;
    void commit(draft.trim(), generation.current);
  };
  const remove = () => {
    cancel(); setDraft("");
    void commit("", generation.current);
  };
  return { draft, busy, edit, flush, remove };
}
