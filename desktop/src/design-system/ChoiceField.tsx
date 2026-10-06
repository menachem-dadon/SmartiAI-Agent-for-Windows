import { useId, useLayoutEffect, useRef } from "react";
import { Button, Popover } from "./primitives";
import { Icon } from "./icons";

type Choice = { value: string; label: string; disabled?: boolean };
type ChoiceFieldProps = {
  label: string;
  hiddenLabel?: boolean;
  id?: string;
  value: string;
  options: readonly Choice[];
  onValueChange: (value: string) => void;
  disabled?: boolean;
  hint?: string;
  error?: string;
};

export function ChoiceField({ label, hiddenLabel = false, id: suppliedId, value, options, onValueChange, disabled, hint, error }: ChoiceFieldProps) {
  const generatedId = useId(), id = suppliedId || generatedId;
  const selectedLabel = options.find(option => option.value === value)?.label || value || "בחירת אפשרות";
  const description = [`${id}-value`, hint ? `${id}-hint` : undefined, error ? `${id}-error` : undefined].filter(Boolean).join(" ");
  return <div className="sds-field-group sds-choice-field">
    <label className={hiddenLabel ? "sds-visually-hidden" : undefined} htmlFor={id}>{label}</label>
    <Popover label={label} className="sds-choice-popover" matchTriggerWidth
      triggerProps={{ id, disabled: disabled || !options.some(option => !option.disabled), "aria-describedby": description, "aria-invalid": error ? true : undefined }}
      triggerContent={<span className="sds-choice-trigger-content">
        {/* All labels share one grid cell so the widest rendered option sizes the button. */}
        <span className="sds-choice-width-labels" aria-hidden="true">{options.map(option => <bdi key={option.value}>{option.label}</bdi>)}</span>
        <bdi id={`${id}-value`}>{selectedLabel}</bdi>
      </span>}>
      {close => <ChoiceOptions label={label} value={value} options={options} onSelect={next => { close(); onValueChange(next); }} close={close} />}
    </Popover>
    {hint && <p className="sds-hint" id={`${id}-hint`}>{hint}</p>}
    {error && <p className="sds-field-error" role="alert" id={`${id}-error`}>{error}</p>}
  </div>;
}

function ChoiceOptions({ label, value, options, onSelect, close }: { label: string; value: string; options: readonly Choice[]; onSelect: (value: string) => void; close: () => void }) {
  const list = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const selected = list.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]:not(:disabled)');
    (selected || list.current?.querySelector<HTMLButtonElement>('button:not(:disabled)'))?.focus();
  }, []);
  return <div ref={list} role="listbox" aria-label={label} className="sds-choice-options" onKeyDown={event => {
    if (event.key === "Tab") { close(); return; }
    const choices = [...(list.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])];
    const index = choices.indexOf(document.activeElement as HTMLButtonElement);
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && choices.length) {
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + choices.length) % choices.length;
      choices[next].focus();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.altKey && event.key !== " ") {
      [...choices.slice(index + 1), ...choices.slice(0, index + 1)].find(choice => choice.textContent?.trim().toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()))?.focus();
    }
  }}>
    {options.map(option => <Button key={option.value} role="option" variant="ghost" aria-selected={option.value === value} tabIndex={-1} disabled={option.disabled}
      className="sds-choice-option" onClick={() => onSelect(option.value)}>
      <bdi>{option.label}</bdi><Icon name="check" className={option.value === value ? undefined : "sds-choice-check-hidden"} />
    </Button>)}
  </div>;
}
