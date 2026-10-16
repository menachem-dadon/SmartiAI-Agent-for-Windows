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
  }).slice(0, 8);
}

export function highlightParts(text: string, query: string): { text: string; match: boolean }[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [{ text, match: false }];
  const source = text.toLocaleLowerCase();
  const parts = [];
  let cursor = 0;
  let index = source.indexOf(needle);
  while (index >= 0) {
    if (index > cursor) parts.push({ text: text.slice(cursor, index), match: false });
    parts.push({ text: text.slice(index, index + needle.length), match: true });
    cursor = index + needle.length;
    index = source.indexOf(needle, cursor);
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false });
  return parts;
}

export type SearchFile = { name: string; path: string; size: number; modified_at: string };
