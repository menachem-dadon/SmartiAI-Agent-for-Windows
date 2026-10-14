import { useEffect, useRef, useState } from "react";
import { Button, Icon, Popover } from "./design-system";
import { providerOptions } from "./managementCatalog";
import { ManagementFeedback } from "./managementFeedback";
import { ProviderIcon } from "./ProviderIcon";

function ProviderChoice({ value, label }: { value: string; label: string }) {
  return <span className="source-provider-choice" dir="rtl">
    <ProviderIcon value={value} />
    <bdi>{label}</bdi>
  </span>;
}

export function ProviderPicker({ value, onSelect }: { value: string; onSelect: (provider: string) => Promise<void> }) {
  const selected = providerOptions.find(option => option.value === value);
  const label = selected?.label || value;
  return <div className="source-provider-picker" data-provider={value}>
    <Popover label={`ספק המודל: ${label}`} className="source-provider-popover" matchTriggerWidth triggerContent={
      <span className="source-provider-trigger-content">
        {/* Overlaid labels size the trigger with the actual font, regardless of selection. */}
        <span className="source-provider-width-labels" aria-hidden="true">
          {providerOptions.map(option => <bdi key={String(option.value)}>{option.label}</bdi>)}
        </span>
        <ProviderChoice value={value} label={label} />
      </span>
    }>
      {close => <ProviderChoices value={value} onSelect={onSelect} close={close} />}
    </Popover>
  </div>;
}

function ProviderChoices({ value, onSelect, close }: { value: string; onSelect: (provider: string) => Promise<void>; close: () => void }) {
  const list = useRef<HTMLDivElement>(null);
  const [pending, setPending] = useState(false), [error, setError] = useState("");
  useEffect(() => { list.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus(); }, []);
  const choose = async (provider: string) => {
    if (pending) return;
    setPending(true); setError("");
    try { await onSelect(provider); close(); }
    catch (reason) { setError(`בחירת הספק נכשלה: ${String(reason)}`); }
    finally { setPending(false); }
  };
  return <div className="source-provider-popup">
    <ManagementFeedback message={error} />
    <div ref={list} role="listbox" aria-label="ספקי מודלים" aria-busy={pending} onKeyDown={event => {
      if (event.key === "Tab") { close(); return; }
      const choices = [...(list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]:not(:disabled)') || [])];
      const index = choices.indexOf(document.activeElement as HTMLButtonElement);
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && choices.length) {
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + choices.length) % choices.length;
        choices[next].focus();
      } else if (event.key.length === 1 && !event.ctrlKey && !event.altKey && event.key !== " ") {
        const following = [...choices.slice(index + 1), ...choices.slice(0, index + 1)];
        following.find(choice => choice.textContent?.trim().toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()))?.focus();
      }
    }}>
      {providerOptions.map(option => {
        const provider = String(option.value), selected = provider === value;
        return <Button key={provider} role="option" variant="ghost" aria-selected={selected} tabIndex={selected ? 0 : -1} disabled={pending}
          className="source-provider-option" data-provider={provider} onClick={() => void choose(provider)}>
          <ProviderChoice value={provider} label={option.label} /><Icon name="check" className={selected ? undefined : "source-provider-check-hidden"} />
        </Button>;
      })}
    </div>
  </div>;
}
