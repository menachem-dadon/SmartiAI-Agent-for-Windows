import { IconButton } from "./design-system";
import type { BrowserActivity } from "./BrowserPanel";

export function BrowserPreviewCard({ activity, onOpen, onDismiss }: {
  activity: BrowserActivity;
  onOpen: () => void;
  onDismiss: () => void;
}) {
  return <aside className="browser-preview-card" aria-label="תצוגה מקדימה של הדפדפן">
    <header>
      <span className={`browser-preview-status${activity.loading ? " is-loading" : ""}`} aria-label={activity.loading ? "הדפדפן טוען" : "דפדפן פעיל"} />
      <strong title={activity.title}>{activity.title || "דפדפן"}</strong>
      <IconButton icon="expand" label="הרחבת תצוגת הדפדפן" onClick={onOpen} />
      <IconButton icon="close" tooltip={false} label="סגירת התצוגה המקדימה" onClick={onDismiss} />
    </header>
    <button type="button" className="browser-preview-image" aria-label={`פתיחת ${activity.title || "הדפדפן"}`} onClick={onOpen}>
      {activity.previewDataUrl
        ? <img src={activity.previewDataUrl} alt={`תצוגה מקדימה של ${activity.title || "הדפדפן"}`} draggable={false} />
        : <span className="browser-preview-placeholder" role="status">{activity.loading ? "טוען את העמוד…" : activity.previewError || "מכין תצוגה מקדימה…"}</span>}
    </button>
    <small dir="ltr" title={activity.url}>{activity.url}</small>
  </aside>;
}
