import { Icon } from "./design-system";
import "./providerIcons.css";
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

export function ProviderIcon({ value }: { value: string }) {
  const artwork = providerArtwork[value];
  return artwork ? artwork.monochrome
    ? <span className="source-provider-icon source-provider-icon--mono" aria-hidden="true" style={{ maskImage: `url("${artwork.src}")`, WebkitMaskImage: `url("${artwork.src}")` }} />
    : <img className="source-provider-icon" src={artwork.src} alt="" aria-hidden="true" draggable={false} />
    : <Icon name="plug" />;
}
