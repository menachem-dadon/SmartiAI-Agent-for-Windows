type Node = { type: string; value?: string; position?: { start: { offset?: number } }; children?: Node[]; tagName?: string; properties?: Record<string, unknown> };
export type RevealRange = { start: number; end: number; started?: number; spread?: number };
type Grapheme = { segment: string; index: number };
type Segments = Iterable<Grapheme> & { containing(index: number): Grapheme | undefined };
const Segmenter = (Intl as typeof Intl & { Segmenter?: new (locale: undefined, options: { granularity: "grapheme" }) => { segment(text: string): Segments } }).Segmenter;
const segmenter = Segmenter ? new Segmenter(undefined, { granularity: "grapheme" }) : undefined;
function graphemes(text: string): Grapheme[] {
  if (segmenter) return [...segmenter.segment(text)];
  let index = 0;
  return Array.from(text, segment => { const item = { segment, index }; index += segment.length; return item; });
}
export function revealRange(start: number, end: number, previous?: RevealRange): RevealRange {
  const started = Date.now();
  // Interpolate within the real arrival interval. Every glyph is rendered
  // immediately; earlier letters merely start farther along the same fade.
  return { start, end, started, spread: Math.min(160, Math.max(0, started - (previous?.started ?? started - 120))) };
}
// Transform only appended text nodes. Existing Markdown elements keep their
// identity, including tables, code controls and links.
export function streamReveal(options: { ranges: RevealRange[] }) {
  return (tree: Node) => {
    const visit = (node: Node) => {
      if (!node.children) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== "text" || !child.value || child.position?.start.offset == null) { visit(child); return [child]; }
        const offset = child.position.start.offset, value = child.value;
        const now = Date.now();
        const ranges = options.ranges.filter(range => range.end > offset && range.start < offset + value.length && now - (range.started ?? now) < 1000);
        if (!ranges.length) return [child];
        const boundaries = segmenter?.segment(value);
        let cursor = 0; const parts: Node[] = [];
        for (const range of ranges) {
          const rawStart = Math.max(0, range.start - offset), rawEnd = Math.min(value.length, range.end - offset);
          const last = boundaries?.containing(rawEnd - 1);
          const start = Math.max(cursor, boundaries?.containing(rawStart)?.index ?? rawStart);
          const end = last ? last.index + last.segment.length : rawEnd;
          if (start > cursor) parts.push({ type: "text", value: value.slice(cursor, start) });
          if (end > start) {
            const letters = graphemes(value.slice(start, end));
            for (const letter of letters) {
              const elapsed = Math.max(0, now - (range.started ?? now));
              const remaining = Math.max(0, range.end - (offset + start + letter.index + letter.segment.length));
              const lead = (range.spread || 0) * remaining / (range.end - range.start);
              parts.push({ type: "element", tagName: "span", properties: { className: ["stream-reveal"], "data-reveal-offset": offset + start + letter.index, "data-reveal-started": now - elapsed - lead }, children: [{ type: "text", value: letter.segment }] });
            }
          }
          cursor = Math.max(cursor, end);
        }
        if (cursor < value.length) parts.push({ type: "text", value: value.slice(cursor) });
        return parts;
      });
    };
    visit(tree);
  };
}
