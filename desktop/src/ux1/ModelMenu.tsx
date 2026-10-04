import { useRef, useState } from "react";
import { models } from "./data";
import { Icon } from "./Icon";
import { HoverLabel } from "./HoverLabel";

// UX-1 composition of Composer's model menu: favorites plus active fallback,
// provider browsing independent from selection, two scrolling columns, then
// the active model's reasoning and quota footer. No production catalog calls.
export function ModelMenu({ selected, favorites, reasoning, onSelect, onReasoning }: {
  selected: string; favorites: string[]; reasoning: string;
  onSelect: (id: string) => void; onReasoning: (value: string) => void;
}) {
  const active = models.find(item => item.id === selected)!;
  const favoriteModels = favorites.map(id => models.find(item => item.id === id)).filter((item): item is typeof active => !!item);
  const menuModels = favorites.includes(selected) ? favoriteModels : [active, ...favoriteModels];
  const providers = Array.from(new Set(menuModels.map(item => item.provider)));
  const [browsedProvider, setBrowsedProvider] = useState(active.provider);
  const shownProvider = providers.includes(browsedProvider) ? browsedProvider : providers[0];
  const root = useRef<HTMLDivElement>(null);
  return <div ref={root} className="ux-model-menu" onKeyDown={event => {
    if ((event.target as HTMLElement).closest("select")) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const target = event.key === "ArrowLeft"
        ? root.current?.querySelector<HTMLButtonElement>('.ux-model-list [role="menuitemradio"]')
        : root.current?.querySelector<HTMLButtonElement>('.ux-provider-list [aria-pressed="true"]');
      if (target) { event.preventDefault(); target.focus(); }
    }
    if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      const column = (event.target as HTMLElement).closest(".ux-model-column");
      if (!column) return;
      const buttons = Array.from(column.querySelectorAll<HTMLButtonElement>("button"));
      const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      event.preventDefault(); buttons[index]?.focus();
    }
  }}>
    <p className="ux-model-scope">בחירה לשיחה הזו</p>
    <div className="ux-model-columns">
      <section className="ux-model-column ux-provider-column" aria-label="ספקים"><div className="ux-provider-list">{providers.map(provider => <button key={provider} type="button" aria-pressed={shownProvider === provider} onMouseEnter={() => setBrowsedProvider(provider)} onFocus={() => setBrowsedProvider(provider)} onClick={() => setBrowsedProvider(provider)}><HoverLabel text={provider} /><Icon name="chevron" size={14} /></button>)}</div></section>
      <section className="ux-model-column" aria-label="מודלים של הספק"><div className="ux-model-list" role="menu" aria-label={`מודלים של ${shownProvider}`} key={shownProvider}>{menuModels.filter(item => item.provider === shownProvider).map(item => <button key={item.id} type="button" role="menuitemradio" aria-checked={item.id === selected} title={item.name} onClick={() => onSelect(item.id)}><HoverLabel text={item.name} />{item.id === selected && <Icon name="check" size={16} />}</button>)}</div></section>
    </div>
    <footer className="ux-model-footer"><label>עוצמת חשיבה<select aria-label="רמת חשיבה" value={reasoning} onChange={event => onReasoning(event.target.value)}><option>אוטומטי</option><option>רגילה</option><option>מעמיקה</option><option>מרבית</option></select></label>{active.providerId === "openai_codex_signin" && <section className="ux-model-quota" aria-label="מכסת Codex שנותרה">{["5 שעות", "שבוע"].map(period => <div key={period}><span>{period}<b>—</b></span><small>נתוני מכסה אינם זמינים</small></div>)}</section>}</footer>
    {!favorites.length && <p className="ux-popup-note">אפשר להוסיף מודלים מועדפים בהגדרות. המודל הפעיל נשאר זמין.</p>}
  </div>;
}
