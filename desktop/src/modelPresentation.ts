import type { ReasoningOption } from "./chatTypes";

// Presentation only: model IDs, including local paths and third-party namespaces,
// must reach Core unchanged.
export function modelDisplayName(provider: string, model: string) {
  const name = provider.toLowerCase() === "local" ? model.slice(model.lastIndexOf("\\") + 1) : model;
  return name.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
}

const effortNames: Record<string, string> = {
  auto: "Auto", none: "None", minimal: "Minimal", low: "Low",
  medium: "Medium", high: "High", xhigh: "Extra High", max: "Max",
};

// Also handles a still-running Core that returns the previous Hebrew labels.
// The option values and provider-specific list remain authoritative.
export function reasoningDisplayName(value: string, options: ReasoningOption[] = []) {
  return effortNames[value] || options.find(option => option.value === value)?.label || value;
}
