import { useEffect } from "react";
import { agentToolIconName } from "../agentToolIcons";
import { candidateIconForAsset, rasterIcon, toolIcons, type IconName } from "./Icon";
import type { Theme } from "./data";

// Style reused product controls only inside the prototype. Keep the original
// React children, callbacks, semantics and tool IDs; replace their artwork.
export function useRasterIcons(theme: Theme) {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>(".ux-prototype"); if (!root) return;
    root.style.setProperty("--ux-close-icon", `url("${rasterIcon(theme, "close")}")`);
    root.style.setProperty("--ux-browser-icon", `url("${rasterIcon(theme, "browser")}")`);
    root.style.setProperty("--ux-lock-icon", `url("${rasterIcon(theme, "lock")}")`);
    root.style.setProperty("--ux-info-icon", `url("${rasterIcon(theme, "info")}")`);
    const decorate = () => {
      root.querySelectorAll<HTMLElement>(".browser-tabs .tab-dot,.browser-tabs .guest-dot").forEach(dot => {
        const glyph = dot.textContent?.trim();
        const name = glyph === "!" ? "alert" : glyph === "♪" ? "speaker" : glyph === "◌" ? "loader" : glyph === "◆" ? "pin" : dot.classList.contains("guest-dot") ? "user" : "browser";
        dot.style.setProperty("--ux-tab-icon", `url("${rasterIcon(theme, name)}")`);
        dot.dataset.loading = String(glyph === "◌");
      });
      root.querySelectorAll<HTMLImageElement>("img.legacy-icon").forEach(img => {
        const name = candidateIconForAsset(img.getAttribute("src") || "") ?? img.dataset.uxIcon as IconName | undefined;
        if (!name) return;
        img.dataset.uxIcon = name;
        const src = rasterIcon(theme, name); if (img.getAttribute("src") !== src) img.setAttribute("src", src);
      });
      root.querySelectorAll<HTMLElement>(".ux-product-management button, .ux-product-workbench button, .management-dialog button, .ux-native-menu button, .message-actions button, .message-table-actions button").forEach(button => {
        delete button.dataset.demoIcon; delete button.dataset.rasterOnly;
        button.style.removeProperty("--demo-icon");
        const text = button.textContent?.trim() || "";
        const compact = !!button.closest('.message-table-actions, .ux-management-body[data-section="memory"] .management-cards article footer, .ux-management-body[data-section="tasks"] .management-cards article footer') || !!button.closest('.ux-product-management') && /^(רענן|רענון|ניקוי נתונים|נקה נתונים)$/.test(text);
        const memoryToolbar = !!button.closest('.ux-management-body[data-section="memory"] .inline-actions') && !button.closest('article');
        if (compact) {
          button.dataset.compactAction = "true";
          // Original children and handlers remain intact. Text is the accessible
          // name/tooltip, while the candidate renders its semantic PNG only.
          if (text) { button.setAttribute("aria-label", text); button.setAttribute("title", text); }
        }
        if (button.querySelector("img")) return;
        const label = button.getAttribute("aria-label") || button.getAttribute("title") || button.textContent?.trim() || "";
        const toolName = button.closest(".source-tool-row")?.querySelector("input")?.getAttribute("aria-label")?.replace(/^(כבה|הפעל)\s/, "");
        const iconOnly = compact || text === "i" || !/[\p{L}\p{N}]/u.test(text);
        const name: IconName | undefined = button.classList.contains("source-tool-name") && toolName ? toolIcons[agentToolIconName({ name: toolName })] ?? "tools"
          : !iconOnly && !memoryToolbar ? undefined
          : text === "i" || /מידע|עזרה|הסבר/.test(label) ? "info"
          : /פרטים/.test(label) ? "info"
          : /הצמד/.test(label) ? "pin"
          : /ארכב|ארכוב/.test(label) ? "archive"
          : /השהה|השהיה/.test(label) ? "pause"
          : /הרץ|הפעלה|הפעל|המשך/.test(label) ? "play"
          : compact && /ביטול/.test(label) ? "stop"
          : /שחזור/.test(label) ? "refresh"
          : /עצור|עציר/.test(label) ? "stop"
          : /סגיר|ביטול|×|✕/.test(label) ? "close"
          : /טעינה מחדש|רענ|מחדש|ניסיון/.test(label) ? "refresh"
          : /מחיק|מחק|נקה|הסר/.test(label) ? "trash"
          : /הורד|ייצוא|יצוא/.test(label) ? "download"
          : /ייבוא/.test(label) ? "paste"
          : /העתק/.test(label) ? "copy"
          : /חפש|חיפוש/.test(label) ? "search"
          : /סימני|סימנייה|☆/.test(label) ? "star"
          : /תפריט|⋮/.test(label) ? "more"
          : /קדימה/.test(label) ? "forward"
          : /⇦|←|אחור|חזרה/.test(label) ? "back"
          : /בית/.test(label) ? "home"
          : /הוסף|הוספ|חדש|חדשה|יציר|\+|＋/.test(label) ? "plus"
          : /עריכ|ערוך/.test(label) ? "rename"
          : undefined;
        if (!name) return;
        button.dataset.demoIcon = "true";
        button.style.setProperty("--demo-icon", `url("${rasterIcon(theme, name)}")`);
        if (iconOnly) button.dataset.rasterOnly = "true";
      });
      root.querySelectorAll<HTMLElement>('.settings-status,.management-notice,[role="status"]').forEach(node => {
        const text = node.textContent?.trim() || '';
        node.toggleAttribute('data-review-quiet', /^(הפעולה הושלמה(?: והקטלוג נטען מחדש)?|העדפות.*נשמרו|השינויים נשמרו|ההגדרות נשמרו|הקובץ נשמר|הטבלה הועתקה(?: כטקסט)?|נשמר)[.!]?$/.test(text));
      });
    };
    decorate(); let frame = 0;
    const observer = new MutationObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(decorate); });
    observer.observe(root, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["src"] });
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [theme]);
}
