import { useEffect, useRef, useState } from "react";
import { Button, Icon, Popover } from "./design-system";
import { providerOptions } from "./managementCatalog";
import { ManagementFeedback } from "./managementFeedback";
import anthropic from "./provider-icons/anthropic.svg";
import cerebras from "./provider-icons/cerebras.svg";
import deepseek from "./provider-icons/deepseek.svg";
import gemini from "./provider-icons/google-gemini.svg";
import groq from "./provider-icons/groq.svg";
import huggingface from "./provider-icons/hugging-face.svg";
import local from "./provider-icons/local-server.svg";
import mistral from "./provider-icons/mistral-ai.svg";
import moonshot from "./provider-icons/moonshot-ai.svg";
import nvidia from "./provider-icons/nvidia-nim.svg";
import codex from "./provider-icons/openai-codex.svg";
import openai from "./provider-icons/openai.svg";
import openrouter from "./provider-icons/openrouter.svg";
import perplexity from "./provider-icons/perplexity.svg";
import qwen from "./provider-icons/qwen.svg";
import together from "./provider-icons/together-ai.svg";
import xai from "./provider-icons/xai.svg";
import zhipu from "./provider-icons/zhipu-ai.svg";

// Supplied artwork stays unchanged. Monochrome silhouettes inherit theme contrast.
const providerArtwork: Record<string, { src: string; monochrome?: boolean }> = {
  gemini: { src: gemini }, openai: { src: openai, monochrome: true },
  openai_codex_signin: { src: codex }, anthropic: { src: anthropic, monochrome: true },
  openrouter: { src: openrouter, monochrome: true }, groq: { src: groq, monochrome: true },
  nvidia: { src: nvidia }, cerebras: { src: cerebras, monochrome: true },
  huggingface: { src: huggingface }, deepseek: { src: deepseek }, qwen: { src: qwen },
  zhipu: { src: zhipu }, moonshot: { src: moonshot, monochrome: true },
  mistral: { src: mistral }, together: { src: together }, perplexity: { src: perplexity },
  xai: { src: xai, monochrome: true }, local: { src: local, monochrome: true },
};

function ProviderChoice({ value, label }: { value: string; label: string }) {
  const artwork = providerArtwork[value];
  return <span className="source-provider-choice" dir="rtl">
    {artwork ? artwork.monochrome
      ? <span className="source-provider-icon source-provider-icon--mono" aria-hidden="true" style={{ maskImage: `url("${artwork.src}")`, WebkitMaskImage: `url("${artwork.src}")` }} />
      : <img className="source-provider-icon" src={artwork.src} alt="" aria-hidden="true" draggable={false} />
      : <Icon name="plug" />}
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
