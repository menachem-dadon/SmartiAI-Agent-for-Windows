import type { Conversation } from "./chatTypes";

const VISITS_KEY = "smarti.search.visits.v1";
type Visit = { id: string; searched: boolean };

function readVisits(): Visit[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(VISITS_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item): item is Visit => Boolean(item && typeof item.id === "string" && typeof item.searched === "boolean")).slice(0, 24) : [];
  } catch { return []; }
}

export function rememberConversationVisit(id: string, searched = false) {
  if (!id) return;
  try {
    const visits = readVisits();
    localStorage.setItem(VISITS_KEY, JSON.stringify([{ id, searched: searched || Boolean(visits.find(item => item.id === id)?.searched) }, ...visits.filter(item => item.id !== id)].slice(0, 24)));
  } catch { /* Suggestions remain available from the recent conversation list. */ }
}

export function suggestedConversations(conversations: Conversation[]) {
  const available = new Map(conversations.filter(item => Number(item.message_count) > 0).map(item => [item.id, item]));
  const visits = readVisits();
  const recent = [...conversations].sort((left, right) => (right.updated_at || "").localeCompare(left.updated_at || ""));
  const order = [...visits.filter(item => item.searched).slice(0, 3), ...visits, ...recent];
  const seen = new Set<string>();
  return order.flatMap(item => {
    const conversation = available.get(item.id);
    if (!conversation || seen.has(item.id)) return [];
    seen.add(item.id);
    return [conversation];
  }).slice(0, 9);
}

export function highlightParts(text: string, query: string): { text: string; match: boolean }[] {
  const needle = query.trim();
  if (!needle) return [{ text, match: false }];
  const terms = text.toLocaleLowerCase().includes(needle.toLocaleLowerCase()) ? [needle] : needle.match(/[\p{L}\p{N}_]+/gu) || [needle];
  const pattern = [...new Set(terms)].sort((a, b) => b.length - a.length).map(term => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const parts: { text: string; match: boolean }[] = [];
  let cursor = 0;
  for (const match of text.matchAll(new RegExp(pattern, "giu"))) {
    const index = match.index!;
    if (index > cursor) parts.push({ text: text.slice(cursor, index), match: false });
    parts.push({ text: match[0], match: true });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false });
  return parts;
}

export type SearchFile = { name: string; path: string; size: number; modified_at: string };

export function rankSearchFiles(items: SearchFile[], query: string) {
  const needle = query.trim().toLocaleLowerCase();
  const score = (item: SearchFile) => {
    const name = item.name.toLocaleLowerCase();
    return name === needle ? 4 : name.startsWith(needle) ? 3 : name.includes(needle) ? 2 : 1;
  };
  return [...items].sort((a, b) => score(b) - score(a) || b.modified_at.localeCompare(a.modified_at) || a.path.localeCompare(b.path)).slice(0, 9);
}
