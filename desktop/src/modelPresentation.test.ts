import { expect, test } from "vitest";
import { distinctProviderModels, modelDisplayName, modelIdentity } from "./modelPresentation";

const provider = "google_antigravity_signin";
test("Antigravity variants have one display identity while persisted IDs remain raw", () => {
  const models = ["gemini-3.8-flash-high", "gemini-3.8-flash-low", "gemini-3.8-flash-medium", "claude-sonnet-5-5-high"];
  expect(distinctProviderModels(provider, models)).toEqual([models[0], models[3]]);
  expect(modelDisplayName(provider, models[0])).toBe("gemini 3.8 flash");
  expect(modelIdentity(provider, "gpt-oss-120b-medium")).toBe("gpt-oss-120b");
  expect(models[0]).toBe("gemini-3.8-flash-high");
});
test("other providers and unrecognized suffixes keep their identity", () => {
  expect(modelIdentity("openrouter", "vendor/model-high")).toBe("vendor/model-high");
  expect(modelIdentity(provider, "new-model-v2")).toBe("new-model-v2");
  expect(distinctProviderModels("openai", ["model-high", "model-low"])).toHaveLength(2);
});
