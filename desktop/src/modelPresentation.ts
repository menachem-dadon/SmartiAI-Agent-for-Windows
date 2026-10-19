import type { ReasoningOption } from "./chatTypes";

// Presentation only: model IDs, including local paths and third-party namespaces,
// must reach Core unchanged.
export function modelIdentity(provider: string, model: string) {
  return provider === "google_antigravity_signin" ? model.replace(/-(?:low|medium|high|xhigh|max)$/, "") : model;
}

export function distinctProviderModels(provider: string, models: string[]) {
  const seen = new Set<string>();
  return models.filter(model => {
    const key = modelIdentity(provider, model);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}

export function modelDisplayName(provider: string, model: string) {
  const name = provider.toLowerCase() === "local" ? model.slice(model.lastIndexOf("\\") + 1) : modelIdentity(provider, model);
  return name.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
}

const effortNames: Record<string, string> = {
  auto: "Auto", none: "None", minimal: "Minimal", low: "Low",
  medium: "Medium", high: "High", xhigh: "Extra High", max: "Max",
};

// Also handles a still-running Core that returns the previous Hebrew labels.
// The option values and provider-specific list remain authoritative.
export function reasoningDisplayName(value: string, options: ReasoningOption[] = []) {
  if (value.startsWith("budget:")) return options.find(option => option.value === value)?.label || effortNames[value.slice(7)] || value.slice(7);
  return effortNames[value] || options.find(option => option.value === value)?.label || value;
}

export const isReasoningBudget = (value: string) => value.startsWith("budget:");
export function reasoningModeOptions(value: string, options: ReasoningOption[]) {
  const budget = isReasoningBudget(value);
  return options.filter(option => option.value !== "auto" && isReasoningBudget(option.value) === budget);
}
export function closestReasoningValue(value: string, budget: boolean, options: ReasoningOption[]) {
  const levels = ["none", "minimal", "low", "medium", "high", "xhigh", "max"];
  const rank = (entry: string) => { const i = levels.indexOf(entry.replace(/^budget:/, "")); return i < 0 ? 3 : i; };
  return options.filter(option => isReasoningBudget(option.value) === budget && option.value !== "auto")
    .sort((a,b) => Math.abs(rank(a.value)-rank(value))-Math.abs(rank(b.value)-rank(value)) || rank(a.value)-rank(b.value))[0]?.value;
}
