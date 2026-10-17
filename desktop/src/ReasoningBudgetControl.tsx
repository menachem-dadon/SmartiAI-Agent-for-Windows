import { useId } from "react";
import { Switch } from "./design-system";
import type { ReasoningOption } from "./chatTypes";
import { closestReasoningValue, isReasoningBudget } from "./modelPresentation";

const budgets: Record<string, number> = { none: 0, minimal: 256, low: 1024, medium: 4096, high: 8192, xhigh: 16384, max: -1 };
export function ReasoningBudgetControl({ value, options, onChange }: {
  value: string; options: ReasoningOption[]; onChange: (value: string) => void | Promise<void>;
}) {
  const id = useId(), budget = isReasoningBudget(value);
  if (!options.some(option => isReasoningBudget(option.value))) return null;
  const canToggle = options.some(option => !isReasoningBudget(option.value));
  const count = budgets[value.slice(7)];
  return <div className="reasoning-budget-control" dir="rtl">
    {canToggle && <label className="reasoning-budget-toggle"><span>תקציב חשיבה קשיח</span>
      <Switch size="small" label="תקציב חשיבה קשיח" checked={budget} aria-describedby={budget ? id : undefined}
        onCheckedChange={checked => { const next = closestReasoningValue(value, checked, options); if (next) void onChange(next); }} />
    </label>}
    {budget && <small id={id} className="reasoning-budget-hint">{count === -1 ? "תקציב חשיבה קשיח: ללא תקרה נוספת" : `תקציב חשיבה קשיח: עד ${Number(count).toLocaleString("en-US")} טוקנים`}</small>}
  </div>;
}
