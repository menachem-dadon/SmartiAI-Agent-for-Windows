type Node = { type: string; value?: string; position?: { start: { offset?: number } }; children?: Node[]; tagName?: string; properties?: Record<string, unknown> };
export type RevealRange = { start: number; end: number; started?: number };
// Transform only appended text nodes. Existing Markdown elements keep their
// identity, including tables, code controls and links.
export function streamReveal(options: { ranges: RevealRange[] }) {
  return (tree: Node) => {
    const visit = (node: Node) => {
      if (!node.children) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== "text" || !child.value || child.position?.start.offset == null) { visit(child); return [child]; }
        const offset = child.position.start.offset, value = child.value;
        const ranges = options.ranges.filter(range => range.end > offset && range.start < offset + value.length);
        if (!ranges.length) return [child];
        let cursor = 0; const parts: Node[] = [];
        for (const range of ranges) {
          const start = Math.max(cursor, range.start - offset), end = Math.min(value.length, range.end - offset);
          if (start > cursor) parts.push({ type: "text", value: value.slice(cursor, start) });
          if (end > start) parts.push({ type: "element", tagName: "span", properties: { className: ["stream-reveal"], "data-reveal-offset": offset + start, style: `animation-delay:-${Math.min(1000, Math.max(0, Date.now() - (range.started || Date.now())))}ms` }, children: [{ type: "text", value: value.slice(start, end) }] });
          cursor = Math.max(cursor, end);
        }
        if (cursor < value.length) parts.push({ type: "text", value: value.slice(cursor) });
        return parts;
      });
    };
    visit(tree);
  };
}
