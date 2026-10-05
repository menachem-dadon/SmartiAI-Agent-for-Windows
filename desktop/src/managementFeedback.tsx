import { Alert, LoadingState } from "./design-system";

// Explicit operation outcomes and useful failures remain visible. Routine
// autosave success is silent; it is never used as an operation outcome.
export function ManagementFeedback({ message }: { message: string }) {
  if (!message) return null;
  if (/^(טוען|בודק|מכין|מייבא|מוריד|מנקה|מאפס|שולח בקשת|מבצע)/.test(message))
    return <LoadingState label={message} />;
  const failed = /נכשל|נכשלה|לא נשמר|לא הושלמה|לא ניתן|אינו תקין|אינה תקינה|יש לבחור|יש לאשר|Error|error|failed|אין אפשרות/i.test(message);
  return <Alert title={message} tone={failed ? "danger" : "info"} />;
}
